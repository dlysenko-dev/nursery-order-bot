"""Чат клиент ↔ менеджер в боте (общая переписка с сайтом и Mini App).

Клиент: «Связаться с менеджером» → «Написать сообщение» → текст уходит в чат.
Менеджер/админ: уведомление с кнопкой «Ответить» → ответ попадает клиенту
в бота (если есть Telegram) и в чат-виджет на сайте.
"""
from aiogram import Router, F, Bot
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMIN_IDS
from db import crud
from services.logger import log
from states.states import ChatStates

router = Router()


def chat_write_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Написать сообщение", callback_data="chat_write")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")],
    ])


def chat_reply_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Ответить клиенту", callback_data=f"chat_reply_{user_id}")],
    ])


@router.callback_query(F.data == "chat_write")
async def chat_write_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ChatStates.client_writing)
    await callback.message.answer(
        "✍️ Напишите ваш вопрос одним сообщением — менеджер получит его и ответит здесь же.\n\n"
        "Отмена: /cancel"
    )
    await callback.answer()


@router.message(StateFilter(ChatStates.client_writing))
async def chat_write_done(message: Message, state: FSMContext) -> None:
    if not message.text or message.text.startswith("/"):
        await state.clear()
        return
    user = await crud.get_or_create_user(message.from_user.id, message.from_user.username)
    await crud.add_chat_message(user.id, "client", message.text)
    await crud.ensure_chat_token(user.id)  # чтобы та же переписка была видна на сайте
    await log("chat_message_from_bot", user_id=message.from_user.id, details=message.text[:100])
    await state.clear()
    await message.answer("✅ Сообщение отправлено менеджеру. Ответ придёт в этот чат.")

    # Уведомляем привязанного менеджера или админов — с кнопкой ответа
    recipients = []
    if user.employee_id:
        employee = await crud.get_employee_by_id(user.employee_id)
        if employee and employee.telegram_id and employee.is_active:
            recipients.append(employee.telegram_id)
    if not recipients:
        recipients = list(ADMIN_IDS)
    text = (
        f"💬 <b>Сообщение от клиента</b> (бот)\n\n"
        f"Клиент: {user.full_name or message.from_user.full_name}\n"
        f"Телефон: {user.phone or '—'}\n\n{message.text[:500]}"
    )
    bot: Bot = message.bot
    for tg_id in recipients:
        try:
            await bot.send_message(tg_id, text, reply_markup=chat_reply_kb(user.id), parse_mode="HTML")
        except Exception:
            pass


@router.callback_query(F.data.startswith("chat_reply_"))
async def chat_reply_start(callback: CallbackQuery, state: FSMContext) -> None:
    employee = await crud.get_employee_by_telegram_id(callback.from_user.id)
    if callback.from_user.id not in ADMIN_IDS and not employee:
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    user_id = int(callback.data.replace("chat_reply_", ""))
    user = await crud.get_user_by_id(user_id)
    if not user:
        await callback.answer("Клиент не найден", show_alert=True)
        return
    await state.update_data(chat_user_id=user_id)
    await state.set_state(ChatStates.manager_replying)
    await callback.message.answer(
        f"💬 Ответ клиенту {user.full_name or '—'} ({user.phone or 'без телефона'}).\n"
        f"Напишите текст одним сообщением. Отмена: /cancel"
    )
    await callback.answer()


@router.message(StateFilter(ChatStates.manager_replying))
async def chat_reply_done(message: Message, state: FSMContext) -> None:
    if not message.text or message.text.startswith("/"):
        await state.clear()
        return
    data = await state.get_data()
    user_id = data.get("chat_user_id")
    user = await crud.get_user_by_id(user_id)
    await state.clear()
    if not user:
        await message.answer("Клиент не найден.")
        return
    employee = await crud.get_employee_by_telegram_id(message.from_user.id)
    await crud.add_chat_message(user_id, "manager", message.text, employee_id=employee.id if employee else None)
    await log("chat_reply_from_bot", user_id=message.from_user.id, details=f"user_id={user_id}")
    # Клиенту в Telegram, если он есть; клиент сайта увидит ответ в виджете на сайте
    if user.telegram_id:
        bot: Bot = message.bot
        try:
            await bot.send_message(user.telegram_id, f"💬 Менеджер питомника:\n\n{message.text}")
        except Exception:
            pass
    await message.answer("✅ Ответ отправлен клиенту.")
