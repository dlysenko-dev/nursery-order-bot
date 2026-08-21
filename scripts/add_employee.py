"""Регистрация сотрудника с личной реферальной ссылкой.

Использование (из корня проекта):
    venv/Scripts/python scripts/add_employee.py "Анна"                # ref_code из имени (anna)
    venv/Scripts/python scripts/add_employee.py "Анна" --tg 123456789 # привязка к Telegram (для экрана «Мои клиенты»)
    venv/Scripts/python scripts/add_employee.py "Анна" --code anna25  # свой ref_code
    venv/Scripts/python scripts/add_employee.py --list                # список сотрудников
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import BOT_USERNAME, WEBAPP_SHORT_NAME, WEBAPP_URL
from db.crud import get_or_create_employee, list_employees
from db.database import init_db


def links(ref_code: str) -> list[str]:
    out = []
    if BOT_USERNAME:
        out.append(f"бот:     https://t.me/{BOT_USERNAME}?start=ref_{ref_code}")
        if WEBAPP_SHORT_NAME:
            out.append(f"мини-ап: https://t.me/{BOT_USERNAME}/{WEBAPP_SHORT_NAME}?startapp=ref_{ref_code}")
    if WEBAPP_URL:
        out.append(f"сайт:    {WEBAPP_URL}?ref={ref_code}")
    return out


async def main() -> None:
    parser = argparse.ArgumentParser(description="Регистрация сотрудника с реферальной ссылкой")
    parser.add_argument("name", nargs="?", help="Имя сотрудника")
    parser.add_argument("--tg", type=int, default=None, help="telegram_id сотрудника")
    parser.add_argument("--code", default=None, help="Свой ref_code (по умолчанию — из имени)")
    parser.add_argument("--list", action="store_true", help="Показать всех сотрудников")
    args = parser.parse_args()

    await init_db()

    if args.list:
        employees = await list_employees()
        if not employees:
            print("Сотрудников пока нет.")
            return
        for emp in employees:
            status = "активен" if emp.is_active else "выключен"
            print(f"#{emp.id} {emp.name} ({emp.ref_code}, tg={emp.telegram_id or '—'}, {status})")
            for link in links(emp.ref_code):
                print(f"   {link}")
        return

    if not args.name:
        parser.error("укажите имя сотрудника или --list")

    emp = await get_or_create_employee(args.name, telegram_id=args.tg, ref_code=args.code)
    print(f"Сотрудник: {emp.name}, ref_code={emp.ref_code}, tg={emp.telegram_id or '—'}")
    for link in links(emp.ref_code):
        print(f"  {link}")
    if not links(emp.ref_code):
        print("  (ссылки не собраны: заполните BOT_USERNAME / WEBAPP_URL в .env)")


if __name__ == "__main__":
    asyncio.run(main())
