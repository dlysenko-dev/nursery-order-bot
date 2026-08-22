"""Ответ менеджера клиенту из бота.

Кнопка «✍️ Ответить клиенту» (chat_reply_{user_id}) приходит с каждым сообщением
клиента — и из бота, и с сайта. Ответ сохраняется в общую историю и:
- клиенту с Telegram — приходит в бот;
- клиенту сайта — подхватывается чат-виджетом на его персональной странице.
"""
import html

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS, WEBAPP_URL
from db import crud
from states.states import ChatStates

router = Router()

MAX_MESSAGE_LEN = 2000


@router.callback_query(F.data.startswith("chat_reply_"))
async def chat_reply_start(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    user_id = int(callback.data.replace("chat_reply_", ""))
    user = await crud.get_user_by_id(user_id)
    if not user:
        await callback.answer("Клиент не найден", show_alert=True)
        return
    await state.set_state(ChatStates.manager_replying)
    await state.update_data(chat_user_id=user_id)
    name = html.escape(user.full_name or "клиенту")
    where = "в бот" if user.telegram_id else "на сайт (в его личный чат)"
    await callback.message.answer(
        f"✍️ Ответ клиенту: {name} (id {user_id}), доставка {where}.\n"
        f"Напишите текст одним сообщением. /cancel — отмена."
    )
    await callback.answer()


@router.message(StateFilter(ChatStates.manager_replying), F.text)
async def chat_reply_message(message: Message, state: FSMContext, bot: Bot) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return
    if message.text.strip().startswith("/cancel"):
        await state.clear()
        await message.answer("Ответ отменён.")
        return
    text = message.text.strip()
    if not text or len(text) > MAX_MESSAGE_LEN:
        await message.answer(f"Пустое или слишком длинное сообщение (максимум {MAX_MESSAGE_LEN}). Попробуйте ещё раз:")
        return
    data = await state.get_data()
    user_id = data.get("chat_user_id")
    await state.clear()
    user = await crud.get_user_by_id(user_id)
    if not user:
        await message.answer("Клиент не найден, ответ не отправлен.")
        return

    await crud.add_chat_message(user.id, sender="manager", text=text, via="bot")
    await crud.mark_chat_read_by_manager(user.id)
    await crud.log_event("chat_reply", user_telegram_id=message.from_user.id, details=f"user_id={user.id}")

    delivered_tg = False
    if user.telegram_id:
        try:
            await bot.send_message(
                user.telegram_id,
                f"💬 Ответ менеджера:\n\n{text}",
            )
            delivered_tg = True
        except Exception:
            pass

    if delivered_tg:
        await message.answer(f"✅ Ответ отправлен клиенту {user.full_name or user.id} в Telegram.")
    else:
        link = f"{WEBAPP_URL.rstrip('/')}/client/{user.site_token}" if WEBAPP_URL and user.site_token else ""
        await message.answer(
            f"✅ Ответ сохранён. У клиента нет Telegram — он увидит ответ на своей странице"
            + (f":\n{link}" if link else " (персональная ссылка выдаётся после заказа).")
        )
