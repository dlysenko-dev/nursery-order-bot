"""Эндпоинты кабинета менеджера: ссылки, статистика, клиенты, заказы, экспорт."""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import BOT_USERNAME, WEBAPP_SHORT_NAME, WEBAPP_URL
from db import crud
from web.auth import get_current_employee

router = APIRouter()


def _ref_site_url(ref_code: str) -> str:
    if not WEBAPP_URL:
        return ""
    sep = "&" if "?" in WEBAPP_URL else "?"
    return f"{WEBAPP_URL}{sep}ref={ref_code}"


def _links(employee) -> dict:
    links = {}
    if BOT_USERNAME:
        links["bot"] = f"https://t.me/{BOT_USERNAME}?start=ref_{employee.ref_code}"
        if WEBAPP_SHORT_NAME:
            links["miniapp"] = f"https://t.me/{BOT_USERNAME}/{WEBAPP_SHORT_NAME}?startapp=ref_{employee.ref_code}"
    if WEBAPP_URL:
        links["site"] = _ref_site_url(employee.ref_code)
    return links


@router.get("/cabinet/links")
async def cabinet_links(employee=Depends(get_current_employee)) -> dict:
    """Реферальные ссылки менеджера."""
    return {
        "ref_code": employee.ref_code,
        "links": _links(employee),
    }


@router.get("/cabinet/stats")
async def cabinet_stats(employee=Depends(get_current_employee)) -> dict:
    """Сводная статистика менеджера."""
    stats = await crud.get_employee_stats(employee.id)
    ref_stats = await crud.get_referral_stats(employee.id)
    by_source: dict[str, int] = {"bot": 0, "miniapp": 0, "site": 0}
    orders_by_source: dict[str, int] = {"bot": 0, "miniapp": 0, "site": 0}
    orders_sum_by_source: dict[str, float] = {"bot": 0.0, "miniapp": 0.0, "site": 0.0}
    for order in stats["orders"]:
        src = order.source or "unknown"
        orders_by_source[src] = orders_by_source.get(src, 0) + 1
        orders_sum_by_source[src] = orders_sum_by_source.get(src, 0.0) + order.total_cost
    return {
        "name": employee.name,
        "ref_code": employee.ref_code,
        "links": _links(employee),
        "totals": {
            "visits": ref_stats["total"],
            "clients": len(stats["clients"]),
            "orders": len(stats["orders"]),
            "sum": stats["total"],
        },
        "visits_by_source": ref_stats["by_source"],
        "orders_by_source": orders_by_source,
        "sum_by_source": orders_sum_by_source,
    }


@router.get("/cabinet/clients")
async def cabinet_clients(employee=Depends(get_current_employee)) -> dict:
    """Список клиентов менеджера."""
    stats = await crud.get_employee_stats(employee.id)
    orders_by_user: dict[int, list] = {}
    for order in stats["orders"]:
        orders_by_user.setdefault(order.user_id, []).append(order)
    clients = []
    for user in stats["clients"]:
        user_orders = orders_by_user.get(user.id, [])
        clients.append(
            {
                "id": user.id,
                "full_name": user.full_name or user.username or "Без имени",
                "phone": user.phone or "",
                "telegram_id": user.telegram_id,
                "username": user.username,
                "source": user.source,
                "created_at": user.created_at.strftime("%Y-%m-%d") if user.created_at else None,
                "orders_count": len(user_orders),
                "orders_sum": sum(o.total_cost for o in user_orders),
            }
        )
    return {"clients": clients}


@router.get("/cabinet/orders")
async def cabinet_orders(employee=Depends(get_current_employee)) -> dict:
    """Заказы клиентов менеджера."""
    stats = await crud.get_employee_stats(employee.id)
    orders = []
    for order in stats["orders"]:
        orders.append(
            {
                "id": order.id,
                "created_at": order.created_at.strftime("%Y-%m-%d %H:%M") if order.created_at else None,
                "status": order.status.value,
                "full_name": order.full_name,
                "phone": order.phone,
                "city": order.city,
                "total_cost": order.total_cost,
                "source": order.source,
                "track_number": order.track_number,
            }
        )
    return {"orders": orders}


@router.get("/cabinet/export")
async def cabinet_export(employee=Depends(get_current_employee)) -> StreamingResponse:
    """Выгрузка клиентов менеджера в Excel."""
    from services.export import build_employee_export_xlsx

    data = await build_employee_export_xlsx(employee.id)
    if not data:
        raise HTTPException(status_code=500, detail="Не удалось собрать выгрузку")
    filename = f"clients_{employee.ref_code}.xlsx"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class TrackVisitIn(BaseModel):
    ref_code: str
    source: str = "site"


@router.post("/track/visit")
async def track_visit(data: TrackVisitIn, request) -> dict:
    """Фиксирует переход по реферальной ссылке (для статистики)."""
    employee = await crud.get_employee_by_ref_code(data.ref_code.strip())
    if not employee:
        return {"ok": False}
    await crud.log_referral_event(
        employee_id=employee.id,
        source=data.source,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    return {"ok": True}
