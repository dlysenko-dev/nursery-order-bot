"""Эндпоинты аутентификации: вход/выход/текущий пользователь."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from db.crud import (
    get_employee_by_secret_token,
    get_employee_by_telegram_id,
    get_employee_by_username,
    update_employee_last_login,
)
from web.auth import (
    create_employee_session,
    get_current_employee,
    hash_password,
    require_employee,
    verify_password,
)

router = APIRouter()


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
async def login(data: LoginIn, request: Request) -> dict:
    """Вход по логину/паролю. Возвращает session token и ставит cookie."""
    employee = await get_employee_by_username(data.username.strip())
    if not employee or not verify_password(data.password, employee.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    if not employee.is_active:
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")

    token = await create_employee_session(
        employee_id=employee.id,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    await update_employee_last_login(employee.id)

    resp = JSONResponse({"token": token, "role": employee.role, "name": employee.name})
    resp.set_cookie(
        "session_token",
        token,
        max_age=30 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return resp


@router.post("/auth/logout")
async def logout(session_token: str | None = None) -> dict:
    """Выход: удаляем сессию."""
    from web.auth import delete_session

    if session_token:
        await delete_session(session_token)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("session_token")
    return resp


@router.get("/auth/me")
async def me(employee=Depends(get_current_employee)) -> dict:
    """Текущий авторизованный сотрудник."""
    return {
        "id": employee.id,
        "name": employee.name,
        "username": employee.username,
        "role": employee.role,
        "telegram_id": employee.telegram_id,
        "ref_code": employee.ref_code,
    }


@router.get("/auth/secret/{secret_token}")
async def login_by_secret(secret_token: str, request: Request):
    """Вход по секретной ссылке: ставим cookie и сразу ведём в кабинет.

    Ссылку открывают в браузере, поэтому вместо JSON возвращаем редирект:
    админ — в /admin, менеджер — в /cabinet.
    """
    employee = await get_employee_by_secret_token(secret_token.strip())
    if not employee:
        raise HTTPException(status_code=404, detail="Ссылка недействительна")
    if not employee.is_active:
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")
    token = await create_employee_session(
        employee_id=employee.id,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    await update_employee_last_login(employee.id)
    target = "/admin" if employee.role == "admin" else "/cabinet"
    resp = RedirectResponse(url=target, status_code=303)
    resp.set_cookie(
        "session_token",
        token,
        max_age=30 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return resp
