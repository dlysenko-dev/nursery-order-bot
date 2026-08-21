"""Сброс названий позиций каталога в нумерацию по фото.

product  -> "<Вид> №<photo_number>"
sapling  -> "<Вид> №<photo_number>"  (видно в каталоге, но не заказывается)

Запуск из корня проекта:
    venv/Scripts/python scripts/reset_titles.py
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from db.database import init_db, AsyncSessionLocal
from db.models import CatalogItem, Category

KIND_NAME = {
    "pion": "Пион",
    "lily": "Лилия",
    "phlox": "Флокс",
    "hosta": "Хоста",
    "hydrangea": "Гортензия",
    "chrysanthemum": "Хризантема",
    "allium": "Декоративный лук",
}


async def main() -> None:
    await init_db()
    async with AsyncSessionLocal() as s:
        cats = {c.id: c for c in (await s.execute(select(Category))).scalars().all()}
        items = (await s.execute(select(CatalogItem).order_by(CatalogItem.id))).scalars().all()
        updated = 0
        for item in items:
            cat = cats.get(item.category_id)
            if not cat:
                continue
            kind = KIND_NAME.get(cat.slug, cat.name)
            title = f"{kind} №{item.photo_number}"
            item.title = title
            updated += 1
            print(f"#{item.id} -> {title} ({item.kind})")
        await s.commit()
        print(f"\nОбновлено: {updated}")


if __name__ == "__main__":
    asyncio.run(main())
