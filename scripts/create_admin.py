"""Создание первого администратора.

Запуск из корня проекта:
    venv/Scripts/python scripts/create_admin.py "Имя" --username admin --password secret123
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import secrets
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.database import init_db
from db.crud import create_employee_with_auth, get_employee_by_username
from web.auth import hash_password


async def main() -> None:
    parser = argparse.ArgumentParser(description="Создание администратора")
    parser.add_argument("name", help="Имя администратора")
    parser.add_argument("--username", required=True, help="Логин для входа на сайте")
    parser.add_argument("--password", required=True, help="Пароль")
    parser.add_argument("--tg", type=int, default=None, help="Telegram ID (для автоматического входа в боте)")
    args = parser.parse_args()

    await init_db()

    existing = await get_employee_by_username(args.username)
    if existing:
        print(f"Логин {args.username} уже занят.")
        return

    secret_token = secrets.token_hex(16)
    emp = await create_employee_with_auth(
        name=args.name,
        username=args.username,
        password_hash=hash_password(args.password),
        telegram_id=args.tg,
        role="admin",
        secret_token=secret_token,
    )
    print(f"Создан админ: {emp.name}")
    print(f"  Логин: {emp.username}")
    print(f"  Пароль: {args.password}")
    print(f"  Telegram ID: {emp.telegram_id or '—'}")
    print(f"  Секретная ссылка: /cabinet/{secret_token}")


if __name__ == "__main__":
    asyncio.run(main())
