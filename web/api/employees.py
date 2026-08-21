"""Эндпоинты для сотрудников: реферальные ссылки и статистика по клиентам."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from config import BOT_USERNAME, WEBAPP_SHORT_NAME, WEBAPP_URL
from db.crud import get_employee_by_telegram_id, get_employee_stats
from web.auth import get_tg_user

router = APIRouter()


@router.get("/employee/stats")
async def employee_stats(init_data: str = Query(default="")) -> dict:
    tg_user = get_tg_user(init_data)
    if not tg_user:
        raise HTTPException(status_code=401, detail="Невалидный initData")
    employee = await get_employee_by_telegram_id(tg_user["id"])
    if not employee:
        raise HTTPException(status_code=403, detail="Вы не сотрудник")

    stats = await get_employee_stats(employee.id)
    orders_by_user: dict[int, list] = {}
    for order in stats["orders"]:
        orders_by_user.setdefault(order.user_id, []).append(order)

    clients = []
    for user in stats["clients"]:
        user_orders = orders_by_user.get(user.id, [])
        clients.append(
            {
                "full_name": user.full_name or user.username or "Без имени",
                "phone": user.phone or "",
                "created_at": user.created_at.strftime("%Y-%m-%d") if user.created_at else None,
                "orders_count": len(user_orders),
                "orders_sum": sum(o.total_cost for o in user_orders),
            }
        )

    site_sep = "&" if WEBAPP_URL and "?" in WEBAPP_URL else "?"
    links = {}
    if BOT_USERNAME:
        links["bot"] = f"https://t.me/{BOT_USERNAME}?start=ref_{employee.ref_code}"
        if WEBAPP_SHORT_NAME:
            links["miniapp"] = f"https://t.me/{BOT_USERNAME}/{WEBAPP_SHORT_NAME}?startapp=ref_{employee.ref_code}"
    if WEBAPP_URL:
        links["site"] = f"{WEBAPP_URL}{site_sep}ref={employee.ref_code}"

    return {
        "name": employee.name,
        "ref_code": employee.ref_code,
        "links": links,
        "clients": clients,
        "totals": {
            "clients": len(stats["clients"]),
            "orders": len(stats["orders"]),
            "sum": stats["total"],
        },
    }
