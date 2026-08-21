"""Разовая загрузка обложек бота в Telegram и запись file_id в БД.

Отправляет каждый файл из media/covers/ первому админу (ADMIN_IDS[0]),
получает file_id и сохраняет:
  - <slug>.jpg  -> categories.infographic_file_id
  - welcome.jpg -> settings['welcome_cover_file_id']
  - how_to_order.png -> settings['how_to_order_file_id']

Скрипт идемпотентен: можно перезапускать, file_id просто обновятся.
Запуск из корня проекта: venv/Scripts/python scripts/upload_covers.py
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from aiogram import Bot
from aiogram.types import FSInputFile

from config import ADMIN_IDS, BOT_TOKEN
from db.crud import set_setting, update_category_infographic

COVERS_DIR = PROJECT_ROOT / "media" / "covers"

CATEGORY_SLUGS = ["pion", "lily", "phlox", "hosta", "hydrangea", "chrysanthemum", "allium"]
SETTING_FILES = {
    "welcome.jpg": "welcome_cover_file_id",
    "how_to_order.png": "how_to_order_file_id",
    "catalog.jpg": "catalog_cover_file_id",
}


async def main() -> None:
    if not BOT_TOKEN:
        sys.exit("BOT_TOKEN не задан в .env")
    if not ADMIN_IDS:
        sys.exit("ADMIN_IDS не задан в .env")
    admin_id = ADMIN_IDS[0]

    bot = Bot(token=BOT_TOKEN)
    try:
        me = await bot.get_me()
        print(f"Бот: @{me.username}, загружаем обложки админу id={admin_id}")

        for slug in CATEGORY_SLUGS:
            path = COVERS_DIR / f"{slug}.jpg"
            if not path.exists():
                print(f"!! {path.name} не найден, пропуск")
                continue
            msg = await bot.send_photo(admin_id, FSInputFile(path), caption=f"cover: {slug}")
            file_id = msg.photo[-1].file_id
            await update_category_infographic(slug, file_id)
            print(f"OK категория {slug}: {file_id[:30]}...")

        for filename, setting_key in SETTING_FILES.items():
            path = COVERS_DIR / filename
            if not path.exists():
                print(f"!! {filename} не найден, пропуск")
                continue
            msg = await bot.send_photo(admin_id, FSInputFile(path), caption=f"cover: {setting_key}")
            file_id = msg.photo[-1].file_id
            await set_setting(setting_key, file_id)
            print(f"OK настройка {setting_key}: {file_id[:30]}...")

        print("Готово.")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
