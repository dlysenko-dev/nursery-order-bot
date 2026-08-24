"""Middleware: автопривязка сотрудника по @username при любом обращении к боту.

Не только /start: если сотрудник уже писал боту раньше (до появления привязки)
или просто отправил любое сообщение/нажал кнопку — привязываем его telegram_id.
"""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from db.crud import bind_employee_by_username


class EmployeeBindMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user and user.username:
            try:
                bound = await bind_employee_by_username(user.id, user.username)
                if bound:
                    from services.logger import log

                    await log(
                        "employee_bound_by_username",
                        user_id=user.id,
                        details=f"employee={bound.ref_code} via=middleware",
                    )
            except Exception:
                pass  # привязка не должна ломать обработку сообщения
        return await handler(event, data)
