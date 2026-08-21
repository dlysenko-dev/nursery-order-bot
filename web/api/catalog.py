"""Каталог, позиции и публичный конфиг для веб-фронта."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from config import BOT_USERNAME, DEFAULT_DELIVERY_COST, DEFAULT_PICKUP_ADDRESS, WEBAPP_URL
from db.crud import (
    get_categories,
    get_category_by_slug,
    get_category_items,
    get_item_by_id,
    get_setting,
)
from db.models import CatalogItem

router = APIRouter()


def _item_payload(item: CatalogItem) -> dict:
    slug = item.category.slug
    n = item.photo_number
    return {
        "id": item.id,
        "title": item.title or f"Фото №{n}",
        "kind": item.kind,
        "price": item.price,
        "stock": item.stock,
        "photo_number": n,
        "photo": f"/static/photos/{slug}_{n}.jpg",
        "thumb": f"/static/photos/thumbs/{slug}_{n}.jpg",
    }


@router.get("/catalog")
async def catalog() -> dict:
    categories = await get_categories()
    payload = []
    for cat in categories:
        items = await get_category_items(cat.slug)
        payload.append(
            {
                "slug": cat.slug,
                "name": cat.name,
                "description": cat.description or "",
                "default_price": cat.default_price,
                "items_count": len(items),
                "cover": f"/static/covers/{cat.slug}.jpg",
            }
        )
    return {
        "categories": payload,
        "welcome_cover": "/static/covers/welcome.jpg",
        "catalog_cover": "/static/covers/catalog.jpg",
    }


@router.get("/config")
async def app_config() -> dict:
    delivery_str = await get_setting("delivery_cost")
    return {
        "delivery_cost": float(delivery_str) if delivery_str else DEFAULT_DELIVERY_COST,
        "manager_contact": (await get_setting("manager_contact")) or "",
        "pickup_address": (await get_setting("pickup_address")) or DEFAULT_PICKUP_ADDRESS,
        "bot_username": BOT_USERNAME,
        "webapp_url": WEBAPP_URL,
    }


@router.get("/catalog/{slug}")
async def category(slug: str) -> dict:
    cat = await get_category_by_slug(slug)
    if not cat or not cat.is_active:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    items = await get_category_items(slug)
    return {
        "slug": cat.slug,
        "name": cat.name,
        "description": cat.description or "",
        "default_price": cat.default_price,
        "cover": f"/static/covers/{cat.slug}.jpg",
        "items": [_item_payload(i) for i in items],
    }


@router.get("/item/{item_id}")
async def item(item_id: int) -> dict:
    it = await get_item_by_id(item_id)
    if not it or not it.is_active:
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    payload = _item_payload(it)
    payload["category"] = {"slug": it.category.slug, "name": it.category.name}
    return payload
