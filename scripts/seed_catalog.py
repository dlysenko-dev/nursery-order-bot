"""Разовое наполнение каталога позициями из папки ../цветы/.

Для каждого фото: отправляет админу (ADMIN_IDS[0]) -> file_id ->
создаёт позицию каталога (photo_number по порядку, цена = default_price
категории, stock = DEFAULT_STOCK).

Идемпотентно: позиции, уже существующие в категории (по количеству),
пропускаются — повторный запуск не дублирует.
Запуск из корня проекта: venv/Scripts/python scripts/seed_catalog.py
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
from db.crud import create_catalog_item, get_category_by_slug, get_category_items

FLOWERS_DIR = PROJECT_ROOT.parent / "цветы"
DEFAULT_STOCK = 10

FOLDER_TO_SLUG = {
    "пионы": "pion",
    "лилии": "lily",
    "флоксы": "phlox",
    "хосты": "hosta",
    "гортензия_метельчатая": "hydrangea",
    "хризантемы": "chrysanthemum",
    "лук_декоративный": "allium",
}


async def main() -> None:
    if not BOT_TOKEN or not ADMIN_IDS:
        sys.exit("BOT_TOKEN / ADMIN_IDS не заданы в .env")
    admin_id = ADMIN_IDS[0]
    bot = Bot(token=BOT_TOKEN)
    try:
        for folder, slug in FOLDER_TO_SLUG.items():
            folder_path = FLOWERS_DIR / folder
            photos = sorted(p for p in folder_path.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
            if not photos:
                print(f"!! {folder}: фото не найдены, пропуск")
                continue
            category = await get_category_by_slug(slug)
            existing = await get_category_items(slug, active_only=False)
            skip = len(existing)
            if skip >= len(photos):
                print(f"== {slug}: уже {skip} позиций из {len(photos)} фото, пропуск")
                continue
            print(f"== {slug}: {len(photos)} фото, уже есть {skip}, добавляем {len(photos) - skip}")
            for i, photo_path in enumerate(photos, start=1):
                if i <= skip:
                    continue
                msg = await bot.send_photo(admin_id, FSInputFile(photo_path), caption=f"item: {slug} #{i}")
                file_id = msg.photo[-1].file_id
                await create_catalog_item(
                    category_slug=slug,
                    photo_number=i,
                    price=category.default_price,
                    stock=DEFAULT_STOCK,
                    file_id=file_id,
                )
                print(f"   OK {slug} #{i}")
        print("Готово.")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
