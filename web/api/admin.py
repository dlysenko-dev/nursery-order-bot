"""Эндпоинты админки: управление сотрудниками и общая статистика."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import crud
from web.auth import hash_password, require_admin

router = APIRouter()


class EmployeeOut(BaseModel):
    id: int
    name: str
    username: str | None
    telegram_id: int | None
    ref_code: str
    role: str
    is_active: bool
    last_login_at: str | None
    created_at: str | None


class EmployeeCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    telegram_id: int | None = None
    role: str = "manager"


class EmployeeUpdateIn(BaseModel):
    is_active: bool | None = None
    role: str | None = None
    telegram_id: int | None = None


def _to_out(emp) -> dict:
    return {
        "id": emp.id,
        "name": emp.name,
        "username": emp.username,
        "telegram_id": emp.telegram_id,
        "ref_code": emp.ref_code,
        "role": emp.role,
        "is_active": emp.is_active,
        "last_login_at": emp.last_login_at.strftime("%Y-%m-%d %H:%M") if emp.last_login_at else None,
        "created_at": emp.created_at.strftime("%Y-%m-%d") if emp.created_at else None,
    }


@router.get("/admin/employees")
async def list_employees(employee=Depends(require_admin)) -> dict:
    """Список всех сотрудников."""
    employees = await crud.list_employees()
    return {"employees": [_to_out(e) for e in employees]}


@router.post("/admin/employees")
async def create_employee(data: EmployeeCreateIn, employee=Depends(require_admin)) -> dict:
    """Создать нового сотрудника."""
    existing = await crud.get_employee_by_username(data.username.strip())
    if existing:
        raise HTTPException(status_code=400, detail="Логин уже занят")
    secret_token = secrets.token_hex(16)
    emp = await crud.create_employee_with_auth(
        name=data.name.strip(),
        username=data.username.strip(),
        password_hash=hash_password(data.password),
        telegram_id=data.telegram_id,
        role=data.role,
        secret_token=secret_token,
    )
    return {"employee": _to_out(emp), "secret_token": secret_token}


@router.patch("/admin/employees/{employee_id}")
async def update_employee(employee_id: int, data: EmployeeUpdateIn, employee=Depends(require_admin)) -> dict:
    """Обновить сотрудника: активность, роль, telegram_id."""
    emp = await crud.get_employee_by_id(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    if data.is_active is not None:
        # Избегаем двойного переключения: просто выставляем нужное значение
        if emp.is_active != data.is_active:
            await crud.toggle_employee_active(employee_id)
    if data.role is not None:
        await crud.set_employee_role(employee_id, data.role)
    if data.telegram_id is not None:
        await crud.update_employee_telegram_id(employee_id, data.telegram_id)
    emp = await crud.get_employee_by_id(employee_id)
    return {"employee": _to_out(emp)}


@router.post("/admin/employees/{employee_id}/reset-password")
async def reset_password(employee_id: int, employee=Depends(require_admin)) -> dict:
    """Сгенерировать новый пароль для сотрудника."""
    emp = await crud.get_employee_by_id(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    new_password = secrets.token_urlsafe(10)
    await crud.update_employee_password(employee_id, hash_password(new_password))
    return {"new_password": new_password}


@router.post("/admin/employees/{employee_id}/regenerate-secret")
async def regenerate_secret(employee_id: int, employee=Depends(require_admin)) -> dict:
    """Сгенерировать новую секретную ссылку."""
    emp = await crud.get_employee_by_id(employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    secret_token = secrets.token_hex(16)
    await crud.update_employee_secret_token(employee_id, secret_token)
    return {"secret_token": secret_token}


@router.get("/admin/stats")
async def admin_stats(employee=Depends(require_admin)) -> dict:
    """Общая статистика по всем сотрудникам."""
    employees = await crud.list_employees()
    stats = []
    for emp in employees:
        s = await crud.get_employee_stats(emp.id)
        ref = await crud.get_referral_stats(emp.id)
        stats.append(
            {
                "id": emp.id,
                "name": emp.name,
                "role": emp.role,
                "is_active": emp.is_active,
                "visits": ref["total"],
                "clients": len(s["clients"]),
                "orders": len(s["orders"]),
                "sum": s["total"],
            }
        )
    return {"employees": stats}


@router.get("/admin/overview")
async def admin_overview(employee=Depends(require_admin)) -> dict:
    """Детальная сводка для главной админки: все менеджеры, их клиенты и заказы."""
    return await crud.get_admin_overview()
