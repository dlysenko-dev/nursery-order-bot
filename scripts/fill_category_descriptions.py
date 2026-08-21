"""Переносит описания категорий из handlers/catalog.py (CATEGORY_INFO) в БД.

Заполняет только пустые description — существующие значения не трогает.
Запуск из корня проекта: venv/Scripts/python scripts/fill_category_descriptions.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from db.database import AsyncSessionLocal
from db.models import Category
from handlers.catalog import CATEGORY_INFO


async def main() -> None:
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(Category))
        categories = list(result.scalars().all())
        updated, skipped, missing = 0, 0, []
        for cat in categories:
            info = CATEGORY_INFO.get(cat.slug)
            if not info:
                missing.append(cat.slug)
                continue
            if cat.description:
                skipped += 1
                continue
            cat.description = info
            updated += 1
        await s.commit()
        print(f"Обновлено: {updated}, уже заполнены: {skipped}")
        if missing:
            print("Нет описания в CATEGORY_INFO для:", ", ".join(missing))


if __name__ == "__main__":
    asyncio.run(main())
