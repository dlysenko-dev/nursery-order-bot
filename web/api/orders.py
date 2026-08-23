"""Оформление заказов и профиль клиента (Mini App / сайт)."""
from __future__ import annotations

import html
import re

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from config import ADMIN_IDS, BOT_TOKEN, DEFAULT_PAYMENT_REQUISITES, WEBAPP_URL
from db import crud
from web.auth import get_tg_user

router = APIRouter()


class OrderItemIn(BaseModel):
    item_id: int
    quantity: int = Field(default=1, ge=1)


class OrderIn(BaseModel):
    items: list[OrderItemIn]
    full_name: str = ""
    phone: str = ""
    city: str = ""
    pickup_point: str = ""
    comment: str | None = None
    ref_code: str | None = None
    init_data: str | None = None
    site_token: str | None = None  # вернувшийся клиент сайта — привязываем заказ к нему


def _validate_customer(data: OrderIn) -> list[str]:
    problems = []
    if not data.full_name.strip():
        problems.append("Укажите имя")
    if len(re.sub(r"\D", "", data.phone)) < 10:
        problems.append("Укажите корректный телефон (минимум 10 цифр)")
    if not data.city.strip():
        problems.append("Укажите город")
    if not data.pickup_point.strip():
        problems.append("Укажите пункт выдачи 5Post")
    return problems


async def _notify_admins(order, source: str) -> None:
    """Повторяет паттерн handlers/checkout.py: текст заказа админам + Excel-выгрузка."""
    if not BOT_TOKEN or not ADMIN_IDS:
        return
    try:
        from aiogram import Bot

        lines = [
            f"🔔 <b>Новый заказ №{order.id}</b> ({'Mini App' if source == 'miniapp' else 'сайт'})\n",
            f"Клиент: {html.escape(order.full_name or '')}",
            f"Телефон: {html.escape(order.phone or '')}",
            f"Город: {html.escape(order.city or '')}",
            f"Пункт 5Post: {html.escape(order.pickup_point or '')}",
        ]
        if order.comment:
            lines.append(f"Комментарий: {html.escape(order.comment)}")
        lines.append("")
        for oi in order.items:
            lines.append(
                f"{oi.catalog_item.category.name}, фото №{oi.catalog_item.photo_number} — {oi.quantity} шт."
            )
        lines += [
            "",
            f"Итого: {order.total_cost:.0f} ₽",
            f"К оплате (полностью): {order.prepayment:.0f} ₽",
            "",
            "Статус: ожидается оплата",
        ]
        bot = Bot(token=BOT_TOKEN)
        try:
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, "\n".join(lines), parse_mode="HTML")
                except Exception:
                    pass
            from services.export import send_export_to_admin

            await send_export_to_admin(bot, caption=f"📊 Выгрузка обновлена: новый заказ №{order.id}")
        finally:
            await bot.session.close()
    except Exception as exc:
        print(f"[web] Не удалось уведомить админов о заказе №{order.id}: {exc}")


@router.post("/orders")
async def create_order(data: OrderIn) -> dict:
    problems = _validate_customer(data)
    if problems:
        raise HTTPException(status_code=400, detail=problems)
    if not data.items:
        raise HTTPException(status_code=400, detail=["Корзина пуста"])

    tg_user = get_tg_user(data.init_data or "")
    if tg_user:
        user = await crud.get_or_create_user(tg_user["id"], tg_user.get("username"))
        source = "miniapp"
    elif data.site_token:
        # Вернувшийся клиент сайта: заказ идёт в его существующий профиль
        user = await crud.get_user_by_site_token(data.site_token.strip())
        if not user:
            user = await crud.get_or_create_site_user(data.phone.strip(), data.full_name.strip(), source="site")
        source = "site"
    else:
        user = await crud.get_or_create_site_user(data.phone.strip(), data.full_name.strip(), source="site")
        source = "site"

    employee = None
    if data.ref_code:
        employee = await crud.get_employee_by_ref_code(data.ref_code.strip())
        if employee:
            await crud.assign_employee_to_user(user.id, employee.id)
            await crud.log_referral_event(employee_id=employee.id, source=source, user_id=user.id)

    order, problems = await crud.create_web_order(
        user_id=user.id,
        items=[{"item_id": it.item_id, "quantity": it.quantity} for it in data.items],
        full_name=data.full_name.strip(),
        phone=data.phone.strip(),
        city=data.city.strip(),
        pickup_point=data.pickup_point.strip(),
        comment=(data.comment or "").strip() or None,
        source=source,
        employee_id=employee.id if employee else None,
    )
    if problems or order is None:
        raise HTTPException(status_code=400, detail=problems or ["Не удалось создать заказ"])

    await crud.log_event(
        "order_created_web",
        user_telegram_id=user.telegram_id,
        order_id=order.id,
        details=f"source={source} total={order.total_cost:.0f}",
    )
    await _notify_admins(order, source)

    requisites = (await crud.get_setting("payment_requisites")) or DEFAULT_PAYMENT_REQUISITES
    manager_contact = (await crud.get_setting("manager_contact")) or ""
    pay_url = (
        f"{WEBAPP_URL.rstrip('/')}/pay/{order.pay_token}"
        if WEBAPP_URL and order.pay_token else None
    )
    client_url = (
        f"{WEBAPP_URL.rstrip('/')}/client/{user.site_token}"
        if WEBAPP_URL and user.site_token else None
    )
    return {
        "order_id": order.id,
        "total_cost": order.total_cost,
        "prepayment": order.prepayment,
        "remainder": order.remainder,
        "delivery_cost": order.delivery_cost,
        "payment_requisites": requisites,
        "manager_contact": manager_contact,
        "pay_token": order.pay_token,
        "pay_url": pay_url,
        "site_token": user.site_token,
        "client_url": client_url,
    }


@router.get("/profile")
async def profile(init_data: str = Query(default="")) -> dict:
    """Сохранённые данные клиента для предзаполнения формы (только Mini App)."""
    tg_user = get_tg_user(init_data)
    if not tg_user:
        raise HTTPException(status_code=401, detail="Невалидный initData")
    user = await crud.get_user_by_telegram_id(tg_user["id"])
    if not user:
        return {"full_name": None, "phone": None, "city": None, "pickup_point": None}
    return {
        "full_name": user.full_name,
        "phone": user.phone,
        "city": user.city,
        "pickup_point": user.pickup_point,
    }
