"""Чат клиент → менеджер в боте.

Сообщение сохраняется в общую историю (chat_messages) и пересылается менеджерам
с кнопкой «Ответить клиенту». Ответ менеджера — handlers/admin/chat_reply.py.
"""
from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMIN_IDS
from db import crud
from states.states import ChatStates

router = Router()

MAX_MESSAGE_LEN = 2000


def manager_reply_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✍️ Ответить клиенту", callback_data=f"chat_reply_{user_id}"),
    ]])


async def notify_managers_about_message(bot: Bot, user, text: str, source: str) -> None:
    """Переслать сообщение клиента менеджерам с кнопкой ответа."""
    name = user.full_name or user.username or "Клиент"
    username = f"@{user.username}" if user.username else "—"
    body = (
        f"💬 <b>Сообщение от клиента ({source})</b>\n\n"
        f"От: {name}\nTelegram: {username}\nТелефон: {user.phone or '—'}\n\n"
        f"{text}"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, body, reply_markup=manager_reply_kb(user.id), parse_mode="HTML")
        except Exception:
            pass


@router.callback_query(F.data == "chat_write")
async def chat_write_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ChatStates.client_writing)
    await callback.message.edit_text(
        "✍️ Напишите сообщение менеджеру одним сообщением.\n\n"
        "Ответ придёт сюда, в бот. Если вы оформляли заказ на сайте — "
        "ответ также будет виден на вашей персональной странице.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="← Отмена", callback_data="main_menu"),
        ]]),
    )
    await callback.answer()


@router.message(StateFilter(ChatStates.client_writing), F.text)
async def chat_write_message(message: Message, state: FSMContext, bot: Bot) -> None:
    text = message.text.strip()
    if not text or len(text) > MAX_MESSAGE_LEN:
        await message.answer(f"Сообщение пустое или слишком длинное (максимум {MAX_MESSAGE_LEN} символов). Попробуйте ещё раз:")
        return
    await state.clear()
    user = await crud.get_or_create_user(message.from_user.id, message.from_user.username)
    # Если клиент писал с сайта (тот же телефон) — история уже общая по user_id
    await crud.add_chat_message(user.id, sender="client", text=text, via="bot")
    await crud.log_event("chat_message_bot", user_telegram_id=user.telegram_id, details=f"user_id={user.id}")
    await notify_managers_about_message(bot, user, text, "бот")
    await message.answer(
        "✅ Сообщение отправлено менеджеру.\n\nМы ответим в ближайшее время — ответ придёт прямо сюда.",
    )
