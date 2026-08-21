"""Курация каталога по результатам визуального аудита фото (18.08.2026).

- kind="sapling" — фото саженцев/луковиц/корневищ (показываются отдельно,
  с пометкой «так выглядит посадочный материал»).
- is_active=False — скриншоты с телефона/Авито (неэстетично, скрываем).

Соответствие файл -> photo_number восстанавливается тем же sorted(),
что использовал scripts/seed_catalog.py. Скрипт идемпотентен.
Запуск из корня проекта: venv/Scripts/python scripts/curate_catalog.py
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.crud import get_category_items
from db.database import init_db, AsyncSessionLocal
from db.models import CatalogItem
from sqlalchemy import select

FLOWERS_DIR = PROJECT_ROOT.parent / "цветы"

FOLDER_TO_SLUG = {
    "пионы": "pion",
    "лилии": "lily",
    "флоксы": "phlox",
    "хосты": "hosta",
    "гортензия_метельчатая": "hydrangea",
    "хризантемы": "chrysanthemum",
    "лук_декоративный": "allium",
}

# Имена файлов-саженцев по аудиту (уточнено владельцем: хосты ...2698 и ...2701
# тоже саженцы, хотя файл может выглядеть как взрослый куст)
SAPLING_FILES = {
    "саженец_пиона_ЗКС_IMG_20260814_092316_444.jpg",
    "саженец_пиона_ЗКС_IMG_20260814_092316_448.jpg",
    "саженец_пиона_ЗКС_IMG_20260814_092316_486.jpg",
    "саженец_пиона_ЗКС_IMG_20260814_092316_490.jpg",
    "саженец_пиона_корневище_1000092641.jpg",
    "луковица_лилии_1000092623.jpg",
    "саженец_флокса_1000092612.jpg",
    "саженец_хосты_1000092698.jpg",
    "саженец_хосты_1000092699.jpg",
    "саженец_хосты_1000092700.jpg",
    "саженец_хосты_1000092701.jpg",
    "саженец_хосты_1000092702.jpg",
    "саженец_гортензии_1000092703.jpg",
    "саженец_хризантемы_1000092667.jpg",
    "саженец_хризантемы_1000092668.jpg",
    "саженец_хризантемы_1000092669.jpg",
}

# Скриншоты — скрыть из каталога
SCREENSHOT_FILES = {
    "пион_IMG_20260814_092324_261.jpg",
    "пион_IMG_20260814_092324_338.jpg",
    "лук_декоративный_1000092581.jpg",
}


async def main() -> None:
    await init_db()  # на случай, если миграция колонок ещё не применялась
    async with AsyncSessionLocal() as s:
        sapling_count = hidden_count = 0
        for folder, slug in FOLDER_TO_SLUG.items():
            folder_path = FLOWERS_DIR / folder
            photos = sorted(p.name for p in folder_path.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
            number_by_file = {name: i for i, name in enumerate(photos, start=1)}
            from db.models import Category
            cat = (await s.execute(select(Category).where(Category.slug == slug))).scalar_one()
            items = (await s.execute(select(CatalogItem).where(CatalogItem.category_id == cat.id))).scalars().all()
            file_by_number = {v: k for k, v in number_by_file.items()}
            for item in items:
                filename = file_by_number.get(item.photo_number)
                if filename in SAPLING_FILES and item.kind != "sapling":
                    item.kind = "sapling"
                    sapling_count += 1
                    print(f"sapling: {slug} №{item.photo_number} ({filename})")
                if filename in SCREENSHOT_FILES and item.is_active:
                    item.is_active = False
                    hidden_count += 1
                    print(f"скрыт:   {slug} №{item.photo_number} ({filename})")
        await s.commit()
        print(f"\nГотово: помечено саженцами {sapling_count}, скрыто скриншотов {hidden_count}")


if __name__ == "__main__":
    asyncio.run(main())
