"""Чат клиент ↔ менеджер: общий для сайта, Mini App и бота.

Клиент сайта идентифицируется chat_token (выдаётся при старте чата / заказе,
хранится в localStorage). Клиент Mini App — по initData (chat_token привязывается
к тому же пользователю, поэтому переписка общая). Менеджер — require_employee.
"""
from __future__ import annotations

import html
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from config import ADMIN_IDS, BOT_TOKEN
from db import crud
from web.auth import get_tg_user, require_employee

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatStartIn(BaseModel):
    full_name: str = ""
    phone: str = Field(min_length=5)


class ClientMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    chat_token: str | None = None
    init_data: str | None = None


class ManagerMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


def _msg_view(m) -> dict:
    return {
        "id": m.id,
        "sender": m.sender,
        "text": m.text,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


async def _client_user(chat_token: str | None, init_data: str | None):
    """Клиент по chat_token или по Telegram initData. None → 401."""
    if init_data:
        tg_user = get_tg_user(init_data)
        if tg_user:
            user = await crud.get_user_by_telegram_id(tg_user["id"])
            if user:
                return user
    if chat_token:
        user = await crud.get_user_by_chat_token(chat_token)
        if user:
            return user
    return None


# ---------- Клиентская сторона ----------

@router.post("/chat/client/start")
async def chat_start(data: ChatStartIn) -> dict:
    """Начало чата с сайта: находим/создаём клиента по телефону, выдаём chat_token."""
    user = await crud.get_or_create_chat_user(
        data.phone.strip(), data.full_name.strip() or None, source="site",
    )
    await crud.log_event("chat_started", user_telegram_id=None, details=f"user_id={user.id}")
    return {"chat_token": user.chat_token, "full_name": user.full_name}


@router.get("/chat/client/messages")
async def chat_client_messages(
    chat_token: str | None = Query(default=None),
    init_data: str | None = Query(default=None),
    since_id: int = Query(default=0),
) -> dict:
    user = await _client_user(chat_token, init_data)
    if not user:
        raise HTTPException(status_code=401, detail="Неизвестный клиент")
    messages = await crud.get_chat_messages(user.id, since_id=since_id)
    await crud.mark_chat_read_by_client(user.id)
    token = user.chat_token or await crud.ensure_chat_token(user.id)
    return {
        "chat_token": token,
        "full_name": user.full_name,
        "messages": [_msg_view(m) for m in messages],
    }


@router.post("/chat/client/messages")
async def chat_client_send(data: ClientMessageIn) -> dict:
    user = await _client_user(data.chat_token, data.init_data)
    if not user:
        raise HTTPException(status_code=401, detail="Неизвестный клиент")
    msg = await crud.add_chat_message(user.id, "client", data.text)
    await _notify_manager_about_client_message(user, msg.text)
    token = user.chat_token or await crud.ensure_chat_token(user.id)
    return {"ok": True, "chat_token": token, "message": _msg_view(msg)}


# ---------- Сторона менеджера (кабинет / Mini App) ----------

@router.get("/chat/threads")
async def chat_threads(employee=Depends(require_employee)) -> dict:
    return {"threads": await crud.get_chat_threads()}


@router.get("/chat/threads/{user_id}")
async def chat_thread_messages(
    user_id: int,
    since_id: int = Query(default=0),
    employee=Depends(require_employee),
) -> dict:
    user = await crud.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    messages = await crud.get_chat_messages(user_id, since_id=since_id)
    await crud.mark_chat_read_by_manager(user_id)
    return {
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "phone": user.phone,
            "source": user.source,
            "telegram_id": user.telegram_id,
        },
        "messages": [_msg_view(m) for m in messages],
    }


@router.post("/chat/threads/{user_id}")
async def chat_manager_send(
    user_id: int,
    data: ManagerMessageIn,
    employee=Depends(require_employee),
) -> dict:
    user = await crud.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    msg = await crud.add_chat_message(user_id, "manager", data.text, employee_id=employee.id)
    await crud.log_event("chat_manager_reply", user_telegram_id=employee.telegram_id, details=f"user_id={user_id}")
    await _notify_client(user, f"💬 Менеджер питомника:\n\n{data.text.strip()}")
    return {"ok": True, "message": _msg_view(msg)}


# ---------- Уведомления через бота ----------

async def _notify_manager_about_client_message(user, text: str) -> None:
    """Клиент написал с сайта/мини-апа → привязанному менеджеру или админам в Telegram."""
    if not BOT_TOKEN:
        return
    recipients = []
    if user.employee_id:
        employee = await crud.get_employee_by_id(user.employee_id)
        if employee and employee.telegram_id and employee.is_active:
            recipients.append(employee.telegram_id)
    if not recipients:
        recipients = list(ADMIN_IDS)
    if not recipients:
        return
    body = (
        f"💬 <b>Сообщение от клиента</b> ({'сайт' if user.source == 'site' else 'Mini App'})\n\n"
        f"Клиент: {html.escape(user.full_name or '—')}\n"
        f"Телефон: {html.escape(user.phone or '—')}\n\n"
        f"{html.escape(text[:500])}"
    )
    try:
        from aiogram import Bot
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        reply_markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="💬 Ответить клиенту", callback_data=f"chat_reply_{user.id}")
        ]])
        bot = Bot(token=BOT_TOKEN)
        try:
            for tg_id in recipients:
                try:
                    await bot.send_message(tg_id, body, reply_markup=reply_markup, parse_mode="HTML")
                except Exception as exc:
                    logger.warning("Не удалось уведомить %s о сообщении клиента: %s", tg_id, exc)
        finally:
            await bot.session.close()
    except Exception as exc:
        logger.warning("Не удалось уведомить менеджера: %s", exc)


async def _notify_client(user, text: str) -> None:
    """Менеджер ответил → клиенту в Telegram (если он есть). Клиент сайта увидит ответ в виджете."""
    if not BOT_TOKEN or not user.telegram_id:
        return
    try:
        from aiogram import Bot

        bot = Bot(token=BOT_TOKEN)
        try:
            await bot.send_message(user.telegram_id, text)
        finally:
            await bot.session.close()
    except Exception as exc:
        logger.warning("Не удалось написать клиенту %s: %s", user.telegram_id, exc)
