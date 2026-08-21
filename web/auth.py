"""Аутентификация: Telegram Mini App initData + сессии сотрудников по логину/паролю."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta
from urllib.parse import parse_qsl

from config import BOT_TOKEN

# --- Telegram Mini App initData ---


def parse_init_data(init_data: str) -> dict | None:
    """Разбирает и проверяет initData. Возвращает dict полей (user — уже dict) или None."""
    if not init_data or not BOT_TOKEN:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        return None
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        return None
    user_raw = pairs.get("user")
    if user_raw:
        try:
            pairs["user"] = json.loads(user_raw)
        except (json.JSONDecodeError, TypeError):
            pairs["user"] = None
    return pairs


def get_tg_user(init_data: str) -> dict | None:
    """Возвращает tg-пользователя (id, first_name, username...) из валидного initData или None."""
    data = parse_init_data(init_data)
    if not data:
        return None
    user = data.get("user")
    if isinstance(user, dict) and user.get("id"):
        return user
    return None


# --- Пароли (PBKDF2-HMAC-SHA256, без внешних зависимостей) ---

PBKDF2_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    """Хэширует пароль в формате pbkdf2$iterations$salt$hash (hex)."""
    if not password:
        raise ValueError("Пароль не может быть пустым")
    salt = os.urandom(16)
    iterations = PBKDF2_ITERATIONS
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    """Проверяет пароль против хранимого хэша."""
    if not stored:
        return False
    try:
        algo, iterations_s, salt_hex, hash_hex = stored.split("$", 3)
        if algo != "pbkdf2":
            return False
        iterations = int(iterations_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


# --- Токены ---

def generate_token(length: int = 32) -> str:
    """Генерирует случайный hex-токен."""
    return secrets.token_hex(length)


def generate_secret_token(length: int = 24) -> str:
    """Генерирует токен для секретной ссылки."""
    return secrets.token_hex(length)


# --- Сессии сотрудников ---

SESSION_TTL_DAYS = 30


def session_expires_at() -> datetime:
    return datetime.utcnow() + timedelta(days=SESSION_TTL_DAYS)


async def create_employee_session(employee_id: int, user_agent: str | None = None, ip: str | None = None) -> str:
    """Создаёт сессию и возвращает токен."""
    from db.crud import create_employee_session as crud_create_session

    token = generate_token(32)
    await crud_create_session(
        employee_id=employee_id,
        token=token,
        expires_at=session_expires_at(),
        user_agent=user_agent,
        ip=ip,
    )
    return token


async def get_employee_by_token(token: str):
    """Проверяет сессию по токену и возвращает сотрудника (или None)."""
    from db.crud import get_employee_session, get_employee_by_id, update_employee_last_login

    if not token:
        return None
    session = await get_employee_session(token)
    if not session:
        return None
    if session.expires_at < datetime.utcnow():
        await delete_session(token)
        return None
    employee = await get_employee_by_id(session.employee_id)
    if not employee or not employee.is_active:
        return None
    await update_employee_last_login(employee.id)
    return employee


async def delete_session(token: str) -> None:
    from db.crud import delete_employee_session

    await delete_employee_session(token)


# --- Зависимости FastAPI ---

from fastapi import Cookie, Depends, Header, HTTPException, Query


async def get_current_employee(
    session_token: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
    init_data: str | None = Query(default=None),
):
    """Возвращает сотрудника по cookie/header/initData. Бросает 401, если не авторизован."""
    from db.crud import get_employee_by_telegram_id

    # 1) Telegram Mini App initData
    if init_data:
        tg_user = get_tg_user(init_data)
        if tg_user:
            employee = await get_employee_by_telegram_id(tg_user["id"])
            if employee:
                return employee

    # 2) Bearer token в заголовке
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    # 3) Cookie
    if not token and session_token:
        token = session_token

    if token:
        employee = await get_employee_by_token(token)
        if employee:
            return employee

    raise HTTPException(status_code=401, detail="Требуется авторизация")


async def require_employee(employee=Depends(get_current_employee)):
    """Проверяет, что пользователь — активный сотрудник."""
    if not employee.is_active:
        raise HTTPException(status_code=403, detail="Аккаунт заблокирован")
    return employee


async def require_admin(employee=Depends(require_employee)):
    """Проверяет, что пользователь — админ."""
    if employee.role != "admin":
        raise HTTPException(status_code=403, detail="Требуются права администратора")
    return employee
