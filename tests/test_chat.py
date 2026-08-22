"""Тесты чата клиент ↔ менеджер и сессий сайта (site_token).

Запуск из корня проекта: python tests/test_chat.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

TEST_DB_PATH = pathlib.Path(tempfile.gettempdir()) / "nursery_chat_test.db"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

from db.database import init_db  # noqa: E402
from db import crud  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((name, condition, detail))
    print(f"{'✅' if condition else '❌'} {name}" + (f" — {detail}" if detail else ""))


async def test_sessions() -> None:
    await init_db()

    # Новый клиент сайта сразу получает site_token
    user = await crud.get_or_create_site_user("+79111111111", "Иванова Мария", source="site")
    check("session: site_token выдан при создании", bool(user.site_token))

    # Повторный заказ с тем же телефоном — тот же пользователь и токен
    user2 = await crud.get_or_create_site_user("+79111111111", "Иванова М.", source="site")
    check("session: тот же телефон → тот же пользователь", user2.id == user.id and user2.site_token == user.site_token)

    # Поиск по токену
    found = await crud.get_user_by_site_token(user.site_token)
    check("session: пользователь находится по site_token", found is not None and found.id == user.id)
    not_found = await crud.get_user_by_site_token("несуществующий-токен")
    check("session: чужой токен → 404-эквивалент (None)", not_found is None)

    # Клиент бота тоже получает токен (для единой страницы)
    tg_user = await crud.get_or_create_user(999000111, "tg_client")
    check("session: клиент бота получает site_token", bool(tg_user.site_token))


async def test_chat() -> None:
    user = await crud.get_or_create_site_user("+79222222222", "Петров Пётр", source="site")

    m1 = await crud.add_chat_message(user.id, sender="client", text="Здравствуйте, а когда отправка?", via="site")
    m2 = await crud.add_chat_message(user.id, sender="manager", text="Завтра, трек пришлём", via="bot")
    m3 = await crud.add_chat_message(user.id, sender="client", text="Спасибо!", via="bot")
    check("chat: сообщения сохраняются", all(m.id for m in (m1, m2, m3)))

    history = await crud.get_chat_history(user.id)
    check("chat: история в порядке отправки", [m.id for m in history] == [m1.id, m2.id, m3.id])
    check("chat: отправители сохранены", [m.sender for m in history] == ["client", "manager", "client"])
    check("chat: канал (via) сохранён", history[0].via == "site" and history[1].via == "bot")

    # Инкрементальная загрузка (поллинг виджета)
    fresh = await crud.get_chat_history(user.id, after_id=m2.id)
    check("chat: after_id отдаёт только новые", [m.id for m in fresh] == [m3.id])

    # Флаги прочтения
    unread = await crud.get_unread_chat_user_ids()
    check("chat: непрочитанные клиентские видны менеджеру", user.id in unread)
    await crud.mark_chat_read_by_manager(user.id)
    unread = await crud.get_unread_chat_user_ids()
    check("chat: после прочтения менеджером список пуст", user.id not in unread)

    # Сообщение менеджера ждёт прочтения клиентом
    check("chat: сообщение менеджера изначально непрочитано клиентом", m2.read_by_client is False)
    await crud.mark_chat_read_by_client(user.id)
    history = await crud.get_chat_history(user.id)
    check("chat: после прочтения клиентом флаг выставлен", all(m.read_by_client for m in history if m.sender == "manager"))

    # Изоляция: чужая история не видна
    other = await crud.get_or_create_site_user("+79333333333", "Другой Клиент", source="site")
    other_history = await crud.get_chat_history(other.id)
    check("chat: истории клиентов изолированы", other_history == [])


async def main() -> int:
    await test_sessions()
    await test_chat()

    failed = [r for r in RESULTS if not r[1]]
    print("\n=== ИТОГ ===")
    print(f"Пройдено: {len(RESULTS) - len(failed)} / {len(RESULTS)}")
    if failed:
        print("❌ Провалы:")
        for name, _, detail in failed:
            print(f"  {name} {detail}")
        return 1
    print("✅ Все тесты чата и сессий пройдены")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
