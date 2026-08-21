"""Обёртка над db.crud.log_event."""
from db.crud import log_event as _log

async def log(event: str, user_id: int | None = None, order_id: int | None = None, details: str | None = None) -> None:
    await _log(event=event, user_telegram_id=user_id, order_id=order_id, details=details)
