"""Автогенерация названий позиций каталога (title сейчас пустой).

Для каждой позиции без title берётся название сорта из кураторского списка
VARIETIES по (slug, photo_number % len). Если список исчерпан — «<Вид> №N».

Детерминированно и идемпотентно: заполняются только пустые title.
Списки сортов легко править прямо в этом файле.

Запуск из корня проекта: venv/Scripts/python scripts/generate_titles.py
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

# Название вида в единственном числе (fallback, когда сорта кончились)
KIND_NAME = {
    "pion": "Пион",
    "lily": "Лилия",
    "phlox": "Флокс",
    "hosta": "Хоста",
    "hydrangea": "Гортензия",
    "chrysanthemum": "Хризантема",
    "allium": "Аллиум",
}

# Кураторские списки сортов по категориям (циклически по photo_number)
VARIETIES = {
    "pion": [
        "Сара Бернар", "Коралловый закат", "Ширли Темпл", "Дюшес де Немур",
        "Фестива Максима", "Карл Розенфельд", "Ред Шарм", "Боул оф Бьюти",
    ],
    "lily": [
        "Старгейзер", "Казабланка", "Анита", "Ландини", "Пиксель", "Сибирия",
    ],
    "phlox": [
        "Голубой рай", "Европа", "Наташа", "Снежная королева", "Дракон", "Лиловый туман",
    ],
    "hosta": [
        "Патриот", "Франсис Уильямс", "Голубой ангел", "Сум и Сабстанс", "Хальцион", "Джун",
    ],
    "hydrangea": [
        "Лаймлайт", "Пинки Винки", "Ванилла Фрейз", "Фантом", "Мега Минди", "Полар Бир",
    ],
    "chrysanthemum": [
        "Моне", "Балтика", "Аврора", "Сабо", "Бакарди", "Сталлион",
        "Реган", "Эльбрус", "Терракота", "Свити",
    ],
    "allium": [
        "Гигантеум", "Пёрпл Сенсейшн", "Гладиатор", "Маунт Эверест",
    ],
}

SAPLING_PREFIX = "Саженец: "


async def main() -> None:
    await init_db()
    async with AsyncSessionLocal() as s:
        categories = (await s.execute(select(Category))).scalars().all()
        filled = skipped = 0
        for cat in categories:
            slug = cat.slug
            items = (
                await s.execute(
                    select(CatalogItem)
                    .where(CatalogItem.category_id == cat.id)
                    .order_by(CatalogItem.photo_number)
                )
            ).scalars().all()
            varieties = VARIETIES.get(slug, [])
            for item in items:
                if item.title:
                    skipped += 1
                    continue
                if varieties:
                    variety = varieties[(item.photo_number - 1) % len(varieties)]
                    title = f"{KIND_NAME.get(slug, cat.name)} «{variety}»"
                else:
                    title = f"{KIND_NAME.get(slug, cat.name)} №{item.photo_number}"
                if item.kind == "sapling":
                    title = SAPLING_PREFIX + title
                item.title = title
                filled += 1
                print(f"{slug} #{item.photo_number}: {title}")
        await s.commit()
        print(f"\nГотово: заполнено {filled}, уже было названий {skipped}")


if __name__ == "__main__":
    asyncio.run(main())
