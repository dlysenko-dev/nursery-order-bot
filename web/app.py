"""FastAPI-приложение: сайт + Telegram Mini App.

Запуск из корня проекта: venv/Scripts/python -m uvicorn web.app:app --port 8000
(рабочая директория важна: DATABASE_URL в config.py относительный — ./plant_shop.db)
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from web.api import admin, auth, cabinet, catalog, chat, employees, orders, pay

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Питомник многолетников — веб")

app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(cabinet.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(employees.router, prefix="/api")
app.include_router(pay.router, prefix="/api")
app.include_router(chat.router, prefix="/api")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    # no-store: Telegram WebView агрессивно кэширует — иначе правки не доезжают до мини-апа
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


@app.get("/admin", include_in_schema=False)
async def admin_page() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "admin.html",
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


@app.get("/cabinet", include_in_schema=False)
async def cabinet_page() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "cabinet.html",
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


@app.get("/pay/{pay_token}", include_in_schema=False)
async def pay_page(pay_token: str) -> FileResponse:
    return FileResponse(
        STATIC_DIR / "pay.html",
        headers={"Cache-Control": "no-store, must-revalidate"},
    )


@app.get("/me", include_in_schema=False)
async def me_page() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "cabinet.html",
        headers={"Cache-Control": "no-store, must-revalidate"},
    )
