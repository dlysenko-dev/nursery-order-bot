"""Единый чат клиент ↔ менеджер и персональная страница клиента сайта.

Авторизация — по site_token (персональная ссылка /client/{token}, cookie/localStorage).
Клиенты бота пишут через Telegram (handlers/chat.py), клиенты сайта — через этот API.
История общая: менеджер отвечает из бота, ответ виден и в боте, и на сайте.
"""
from __future__ import annotations

import html
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import ADMIN_IDS, BOT_TOKEN, WEBAPP_URL
from db import crud

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_MESSAGE_LEN = 2000


class ChatMessageIn(BaseModel):
    text: str
    order_id: int | None = None


def _msg_view(m) -> dict:
    return {
        "id": m.id,
        "sender": m.sender,  # client | manager
        "text": m.text,
        "via": m.via,
        "created_at": m.created_at.strftime("%d.%m.%Y %H:%M") if m.created_at else None,
    }


def _order_view(order) -> dict:
    pay_url = f"{WEBAPP_URL.rstrip('/')}/pay/{order.pay_token}" if WEBAPP_URL and order.pay_token else None
    return {
        "order_id": order.id,
        "status": order.status.value,
        "total_cost": order.total_cost,
        "prepayment": order.prepayment,
        "remainder": order.remainder,
        "prepayment_paid": bool(order.prepayment_paid_at),
        "remainder_paid": bool(order.remainder_paid_at),
        "created_at": order.created_at.strftime("%d.%m.%Y %H:%M") if order.created_at else None,
        "pay_url": pay_url,
    }


async def _get_client(site_token: str):
    user = await crud.get_user_by_site_token(site_token)
    if not user:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    return user


@router.get("/client/{site_token}")
async def client_profile(site_token: str) -> dict:
    """Персональная страница клиента: профиль и история заказов."""
    user = await _get_client(site_token)
    orders = await crud.get_orders_by_user(user.id)
    return {
        "full_name": user.full_name,
        "phone": user.phone,
        "city": user.city,
        "orders": [_order_view(o) for o in orders],
    }


@router.get("/client/{site_token}/messages")
async def client_messages(site_token: str, after_id: int = 0) -> dict:
    """История чата (инкрементально по after_id). Помечает сообщения менеджера прочитанными."""
    user = await _get_client(site_token)
    messages = await crud.get_chat_history(user.id, after_id=after_id)
    if messages:
        await crud.mark_chat_read_by_client(user.id)
    return {"messages": [_msg_view(m) for m in messages]}


@router.post("/client/{site_token}/messages")
async def client_send_message(site_token: str, data: ChatMessageIn) -> dict:
    """Сообщение от клиента сайта: сохраняем и пересылаем менеджерам в бот."""
    user = await _get_client(site_token)
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Пустое сообщение")
    if len(text) > MAX_MESSAGE_LEN:
        raise HTTPException(status_code=400, detail=f"Сообщение слишком длинное (максимум {MAX_MESSAGE_LEN} символов)")

    order_id = data.order_id
    if order_id:
        order = await crud.get_order_by_id(order_id)
        if not order or order.user_id != user.id:
            raise HTTPException(status_code=400, detail="Заказ не найден")

    msg = await crud.add_chat_message(user.id, sender="client", text=text, via="site", order_id=order_id)
    await crud.log_event(
        "chat_message_site", user_telegram_id=user.telegram_id,
        details=f"user_id={user.id} len={len(text)}",
    )
    await _notify_managers(user, text, order_id)
    return {"message": _msg_view(msg)}


async def _notify_managers(user, text: str, order_id: int | None = None) -> None:
    """Уведомление админам и менеджерам в Telegram с кнопкой «Ответить»."""
    if not BOT_TOKEN:
        return
    try:
        from aiogram import Bot
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        notify_ids = await crud.get_responsible_notify_ids(user.id)
        if order_id:
            order = await crud.get_order_by_id(order_id)
            if order and order.employee_id:
                notify_ids = await crud.get_responsible_notify_ids(user.id, order_employee_id=order.employee_id)
        if not notify_ids:
            return

        name = html.escape(user.full_name or "Клиент сайта")
        phone = html.escape(user.phone or "—")
        body = (
            f"💬 <b>Сообщение с сайта</b>\n\n"
            f"От: {name}\nТелефон: {phone}\n"
            + (f"Заказ №{order_id}\n" if order_id else "")
            + f"\n{html.escape(text)}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✍️ Ответить клиенту", callback_data=f"chat_reply_{user.id}"),
        ]])
        bot = Bot(token=BOT_TOKEN)
        try:
            for admin_id in notify_ids:
                try:
                    await bot.send_message(admin_id, body, reply_markup=kb, parse_mode="HTML")
                except Exception as exc:
                    logger.warning("Не удалось уведомить менеджера %s: %s", admin_id, exc)
        finally:
            await bot.session.close()
    except Exception as exc:
        logger.warning("Не удалось уведомить менеджеров о сообщении: %s", exc)
