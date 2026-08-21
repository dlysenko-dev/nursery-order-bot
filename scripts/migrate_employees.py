"""Миграция БД: добавление полей аутентификации сотрудникам и новых таблиц.

Запуск из корня проекта:
    venv/Scripts/python scripts/migrate_employees.py
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.database import init_db


async def main() -> None:
    print("Выполняем миграцию employees...")
    await init_db()
    print("Готово. Таблицы employee_sessions и referral_events созданы,")
    print("в employees добавлены username, password_hash, secret_token, role, last_login_at.")


if __name__ == "__main__":
    asyncio.run(main())
