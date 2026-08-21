"""Сборка demo.html — самодостаточного файла для показа/оценки работы.

Один HTML, внутри: CSS + JS фронтенда из web/static/, мок API с реальными
данными каталога из БД, фото в base64 (превью в пониженном качестве).
Работает по двойному клику без сервера (file://).

Запуск из корня проекта: venv/Scripts/python scripts/build_demo.py
"""
from __future__ import annotations

import base64
import io
import json
import pathlib
import sqlite3
import sys

from PIL import Image

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

STATIC = PROJECT_ROOT / "web" / "static"
OUT = PROJECT_ROOT / "demo.html"
DB = PROJECT_ROOT / "plant_shop.db"

COVER_MAX = 900        # px, обложки welcome/catalog/категорий
THUMB_MAX = 360        # px, превью товаров
THUMBS_PER_CATEGORY = 3  # сколько реальных фото на категорию (остальные — заглушка)

PLACEHOLDER = (
    "data:image/svg+xml;utf8," + __import__("urllib.parse", fromlist=["quote"]).quote(
        '<svg xmlns="http://www.w3.org/2000/svg" width="480" height="480">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#1A3027"/><stop offset="1" stop-color="#12231C"/>'
        '</linearGradient></defs><rect width="480" height="480" fill="url(#g)"/>'
        '<text x="240" y="250" font-family="Georgia" font-size="28" fill="#76927F" '
        'text-anchor="middle">фото в полной версии</text></svg>'
    )
)


def b64_image(path: pathlib.Path, max_side: int, quality: int) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    categories = conn.execute(
        "SELECT * FROM categories WHERE is_active = 1 ORDER BY sort_order"
    ).fetchall()
    items = conn.execute(
        "SELECT * FROM catalog_items WHERE is_active = 1 ORDER BY photo_number"
    ).fetchall()
    settings = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}
    conn.close()

    # --- Картинки ---
    cover_welcome = b64_image(STATIC / "covers" / "welcome.jpg", COVER_MAX, 72)
    cover_catalog = b64_image(STATIC / "covers" / "catalog.jpg", COVER_MAX, 72)

    items_by_cat: dict[int, list[sqlite3.Row]] = {}
    for it in items:
        items_by_cat.setdefault(it["category_id"], []).append(it)

    mock: dict[str, object] = {}
    catalog_payload = []
    for cat in categories:
        slug = cat["slug"]
        cover_path = STATIC / "covers" / f"{slug}.jpg"
        cover = b64_image(cover_path, COVER_MAX, 70) if cover_path.exists() else PLACEHOLDER
        cat_items = items_by_cat.get(cat["id"], [])
        catalog_payload.append({
            "slug": slug,
            "name": cat["name"],
            "description": cat["description"] or "",
            "default_price": cat["default_price"],
            "items_count": len(cat_items),
            "cover": cover,
        })
        cat_items_payload = []
        for idx, it in enumerate(cat_items):
            photo_path = STATIC / "photos" / "thumbs" / f"{slug}_{it['photo_number']}.jpg"
            if idx < THUMBS_PER_CATEGORY and photo_path.exists():
                img = b64_image(photo_path, THUMB_MAX, 68)
            else:
                img = PLACEHOLDER
            payload = {
                "id": it["id"],
                "title": it["title"] or f"{cat['name']} №{it['photo_number']}",
                "kind": it["kind"],
                "price": it["price"],
                "stock": it["stock"],
                "photo": img,
                "thumb": img,
            }
            cat_items_payload.append(payload)
            mock[f"/item/{it['id']}"] = {
                **payload,
                "category": {"slug": slug, "name": cat["name"]},
            }
        mock[f"/catalog/{slug}"] = {
            "slug": slug,
            "name": cat["name"],
            "description": cat["description"] or "",
            "default_price": cat["default_price"],
            "items": cat_items_payload,
        }
    mock["/catalog"] = catalog_payload
    mock["/config"] = {
        "delivery_cost": float(settings.get("delivery_cost") or 300),
        "manager_contact": settings.get("manager_contact") or "",
        "pickup_address": settings.get("pickup_address") or "",
        "bot_username": "",
        "webapp_url": "",
    }

    # --- Сборка HTML ---
    tokens_css = (STATIC / "css" / "tokens.css").read_text(encoding="utf-8")
    app_css = (STATIC / "css" / "app.css").read_text(encoding="utf-8")
    tg_js = (STATIC / "js" / "tg.js").read_text(encoding="utf-8")
    app_js = (STATIC / "js" / "app.js").read_text(encoding="utf-8")
    app_js = app_js.replace("/static/covers/welcome.jpg", cover_welcome)
    app_js = app_js.replace("/static/covers/catalog.jpg", cover_catalog)
    logo_b64 = b64_image(STATIC / "covers" / "logo.png", 96, 85)

    fetch_mock = (
        "<script>(function(){var MOCK=" + json.dumps(mock, ensure_ascii=False) + ";"
        "window.fetch=function(url,opts){"
        "if(typeof url==='string'&&url.indexOf('/api')===0){"
        "var path=url.slice(4);var method=(opts&&opts.method)||'GET';var body,status=200;"
        "if(method==='POST'&&path==='/orders'){var plants=0;try{JSON.parse(opts.body).items.forEach(function(it){var item=MOCK['/item/'+it.item_id];plants+=(item?item.price:0)*it.quantity;});}catch(e){}"
        "var del=MOCK['/config'].delivery_cost,total=plants+del,pre=Math.round(total*0.3);"
        "body={order_id:100,total_cost:total,prepayment:pre,remainder:total-pre,delivery_cost:del,"
        "payment_requisites:'Ozon Банк: 89233981917 (демо)',manager_contact:MOCK['/config'].manager_contact};}"
        "else if(Object.prototype.hasOwnProperty.call(MOCK,path)){body=MOCK[path];}"
        "else{status=404;body={detail:'В демо-версии этот запрос недоступен'};}"
        "return Promise.resolve(new Response(JSON.stringify(body),{status:status,headers:{'Content-Type':'application/json'}}));}"
        "return Promise.resolve(new Response('{}',{status:200}));};})();</script>"
    )

    description = """<!--
  ДЕМО: Питомник многолетников — сайт + Telegram Mini App (один фронтенд).
  Самодостаточный файл: фронтенд инлайн, API замокано реальными данными каталога из SQLite,
  фото встроены в base64 (превью пониженного качества; часть карточек — заглушки).

  Что построено:
  - Бэкенд FastAPI (web/): каталог, карточка, создание заказа (резерв остатков,
    уведомление админов в Telegram + Excel), профиль, статистика сотрудника.
    Общая БД с Telegram-ботом (SQLAlchemy + SQLite, WAL).
  - Реферальный учёт: у каждого сотрудника ссылки t.me/<bot>?start=ref_<code>,
    мини-ап ?startapp=ref_<code>, сайт ?ref=<code>; первый источник побеждает;
    экран «Мои клиенты» в Mini App (в демо скрыт — требует Telegram initData).
  - Дизайн-система calm botanical luxury: forest-палитра, glass-карточки (blur 20px),
    ivory pill CTA, Cormorant Garamond + Manrope, сетка 4px, mobile-first, max-width 480px.

  Экраны: welcome → каталог → категория (растения/саженцы) → карточка → корзина
  (доставка 5Post, предоплата 30%) → оформление → успех с реквизитами.
-->"""

    index = (STATIC / "index.html").read_text(encoding="utf-8")
    head_end = index.index("</head>")
    body_start = index.index("<body>")
    body_html = index[body_start + len("<body>"): index.rindex("</body>")]
    # Убираем внешние подключения из тела (скрипты добавим сами)
    body_html = "\n".join(
        line for line in body_html.splitlines() if "<script" not in line
    )
    body_html = body_html.replace("/static/covers/logo.png", logo_b64)

    html = (
        "<!DOCTYPE html>\n<html lang=\"ru\">\n<head>\n<meta charset=\"UTF-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0, viewport-fit=cover\">\n"
        "<meta name=\"theme-color\" content=\"#12231C\">\n"
        "<title>Питомник многолетников — демо</title>\n"
        f"<link rel=\"icon\" type=\"image/png\" href=\"{logo_b64}\">\n"
        "<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">\n"
        "<link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>\n"
        "<link href=\"https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400&family=Manrope:wght@400;500;600;700&display=swap\" rel=\"stylesheet\">\n"
        "<style>\n" + tokens_css + "\n" + app_css + "\n</style>\n"
        + fetch_mock + "\n</head>\n"
        + description + "\n<body>\n"
        + body_html + "\n<script>\n" + tg_js + "\n</script>\n<script>\n" + app_js + "\n</script>\n"
        "</body>\n</html>\n"
    )

    OUT.write_text(html, encoding="utf-8")
    size_kb = OUT.stat().st_size // 1024
    print(f"Собрано: {OUT} ({size_kb} КБ)")
    print(f"Позиций в моке: {len(items)}, категорий: {len(categories)}")


if __name__ == "__main__":
    main()
