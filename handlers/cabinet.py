"""Кабинет сотрудника в Telegram-боте."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import BOT_USERNAME, WEBAPP_SHORT_NAME, WEBAPP_URL
from db import crud
from services.export import build_employee_export_xlsx

router = Router()


def _site_url(ref_code: str) -> str:
    if not WEBAPP_URL:
        return ""
    sep = "&" if "?" in WEBAPP_URL else "?"
    return f"{WEBAPP_URL}{sep}ref={ref_code}"


def _links(employee) -> dict:
    links = {}
    if BOT_USERNAME:
        links["bot"] = f"https://t.me/{BOT_USERNAME}?start=ref_{employee.ref_code}"
        if WEBAPP_SHORT_NAME:
            links["miniapp"] = f"https://t.me/{BOT_USERNAME}/{WEBAPP_SHORT_NAME}?startapp=ref_{employee.ref_code}"
    if WEBAPP_URL:
        links["site"] = _site_url(employee.ref_code)
    return links


def _cabinet_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Реф-ссылки", callback_data="cabinet_links")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="cabinet_stats")],
            [InlineKeyboardButton(text="👥 Клиенты", callback_data="cabinet_clients")],
            [InlineKeyboardButton(text="📦 Заказы", callback_data="cabinet_orders")],
            [InlineKeyboardButton(text="📥 Выгрузить Excel", callback_data="cabinet_export")],
            [InlineKeyboardButton(text="← Назад в меню", callback_data="main_menu")],
        ]
    )


@router.callback_query(F.data == "my_cabinet")
async def show_cabinet(callback: CallbackQuery) -> None:
    employee = await crud.get_employee_by_telegram_id(callback.from_user.id)
    if not employee:
        await callback.answer("Этот раздел доступен только сотрудникам", show_alert=True)
        return
    await callback.message.answer(
        f"👤 *Кабинет сотрудника*\n\n"
        f"Имя: {employee.name}\n"
        f"Код: `{employee.ref_code}`\n"
        f"Роль: {employee.role}\n\n"
        f"Выберите действие:",
        reply_markup=_cabinet_kb(),
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "cabinet_links")
async def cabinet_links(callback: CallbackQuery) -> None:
    employee = await crud.get_employee_by_telegram_id(callback.from_user.id)
    if not employee:
        await callback.answer("Этот раздел доступен только сотрудникам", show_alert=True)
        return
    links = _links(employee)
    text = "🔗 *Ваши реферальные ссылки*\n\n"
    for label, url in links.items():
        text += f"*{label}:*\n`{url}`\n\n"
    text += "Делитесь ссылками — клиенты, пришедшие по ним, закрепятся за вами."
    await callback.message.answer(text, reply_markup=_cabinet_kb(), parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "cabinet_stats")
async def cabinet_stats(callback: CallbackQuery) -> None:
    employee = await crud.get_employee_by_telegram_id(callback.from_user.id)
    if not employee:
        await callback.answer("Этот раздел доступен только сотрудникам", show_alert=True)
        return
    stats = await crud.get_employee_stats(employee.id)
    ref_stats = await crud.get_referral_stats(employee.id)
    text = (
        f"📊 *Статистика*\n\n"
        f"Переходы по ссылкам: *{ref_stats['total']}*\n"
        f"Клиенты: *{len(stats['clients'])}*\n"
        f"Заказы: *{len(stats['orders'])}*\n"
        f"Сумма: *{stats['total']:.0f} ₽*\n\n"
        f"*По источникам:*\n"
    )
    for src, count in ref_stats["by_source"].items():
        text += f"• {src}: {count}\n"
    await callback.message.answer(text, reply_markup=_cabinet_kb(), parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "cabinet_clients")
async def cabinet_clients(callback: CallbackQuery) -> None:
    employee = await crud.get_employee_by_telegram_id(callback.from_user.id)
    if not employee:
        await callback.answer("Этот раздел доступен только сотрудникам", show_alert=True)
        return
    stats = await crud.get_employee_stats(employee.id)
    orders_by_user: dict[int, list] = {}
    for order in stats["orders"]:
        orders_by_user.setdefault(order.user_id, []).append(order)
    text = "👥 *Ваши клиенты*\n\n"
    if not stats["clients"]:
        text += "Пока пусто — поделитесь своей ссылкой."
    else:
        for user in stats["clients"][:10]:
            user_orders = orders_by_user.get(user.id, [])
            total = sum(o.total_cost for o in user_orders)
            text += (
                f"*{user.full_name or user.username or 'Без имени'}*\n"
                f"📞 {user.phone or '—'} · 📅 {user.created_at.strftime('%d.%m.%Y') if user.created_at else '—'}\n"
                f"📦 {len(user_orders)} заказов · 💰 {total:.0f} ₽\n\n"
            )
        if len(stats["clients"]) > 10:
            text += f"... и ещё {len(stats['clients']) - 10} клиентов"
    await callback.message.answer(text, reply_markup=_cabinet_kb(), parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "cabinet_orders")
async def cabinet_orders(callback: CallbackQuery) -> None:
    employee = await crud.get_employee_by_telegram_id(callback.from_user.id)
    if not employee:
        await callback.answer("Этот раздел доступен только сотрудникам", show_alert=True)
        return
    stats = await crud.get_employee_stats(employee.id)
    text = "📦 *Заказы ваших клиентов*\n\n"
    if not stats["orders"]:
        text += "Пока нет заказов."
    else:
        for order in stats["orders"][:10]:
            text += (
                f"№{order.id} · {order.created_at.strftime('%d.%m.%Y') if order.created_at else '—'}\n"
                f"{order.full_name or '—'} · {order.status.value}\n"
                f"💰 {order.total_cost:.0f} ₽ · {order.source or '—'}\n\n"
            )
        if len(stats["orders"]) > 10:
            text += f"... и ещё {len(stats['orders']) - 10} заказов"
    await callback.message.answer(text, reply_markup=_cabinet_kb(), parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "cabinet_export")
async def cabinet_export(callback: CallbackQuery) -> None:
    employee = await crud.get_employee_by_telegram_id(callback.from_user.id)
    if not employee:
        await callback.answer("Этот раздел доступен только сотрудникам", show_alert=True)
        return
    data = await build_employee_export_xlsx(employee.id)
    if not data:
        await callback.answer("Не удалось собрать выгрузку", show_alert=True)
        return
    filename = f"clients_{employee.ref_code}.xlsx"
    await callback.message.answer_document(
        BufferedInputFile(data, filename=filename),
        caption="📥 Выгрузка ваших клиентов",
    )
    await callback.answer()
