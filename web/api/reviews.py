"""Отзывы: отдаём список скриншотов из web/static/assets/reviews.

Как добавить отзыв: просто положить скриншот (jpg/png/webp) в папку
static/assets/reviews — секция на сайте подхватит его автоматически.
"""
import logging
from pathlib import Path

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()

REVIEWS_DIR = Path(__file__).resolve().parent.parent / "static" / "assets" / "reviews"
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}


@router.get("/reviews")
async def list_reviews() -> dict:
    """Список скриншотов отзывов (Авито, мессенджеры). Пустая папка = пустой список, секция на сайте скрыта."""
    if not REVIEWS_DIR.is_dir():
        return {"reviews": []}
    files = sorted(
        (p for p in REVIEWS_DIR.iterdir() if p.suffix.lower() in ALLOWED_EXT),
        key=lambda p: p.name,
    )
    return {"reviews": [{"src": f"/static/assets/reviews/{p.name}"} for p in files]}
