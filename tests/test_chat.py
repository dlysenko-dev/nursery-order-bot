"""Тесты чата клиент ↔ менеджер: пользователи, сообщения, треды, прочтение.

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


async def main() -> int:
    await init_db()

    # 1. Клиент сайта: создание по телефону + chat_token
    user = await crud.get_or_create_chat_user("+79111111111", "Мария Сайтова")
    check("chat: клиент создан с токеном", bool(user.chat_token))
    token1 = user.chat_token

    # 2. Повторный старт с тем же телефоном → тот же пользователь и тот же токен
    user2 = await crud.get_or_create_chat_user("+79111111111", "Мария Сайтова")
    check("chat: тот же телефон → тот же пользователь", user2.id == user.id and user2.chat_token == token1)

    # 3. Поиск по токену
    found = await crud.get_user_by_chat_token(token1)
    check("chat: пользователь находится по chat_token", found is not None and found.id == user.id)

    # 4. Клиент пишет → непрочитано менеджером
    m1 = await crud.add_chat_message(user.id, "client", "Здравствуйте, когда отправка?")
    check("chat: сообщение клиента не прочитано менеджером", not m1.is_read_by_manager and m1.is_read_by_client)

    # 5. Треды: 1 диалог, 1 непрочитанное
    threads = await crud.get_chat_threads()
    check("chat: тред появился", len(threads) == 1 and threads[0]["user_id"] == user.id)
    check("chat: непрочитанных = 1", threads[0]["unread"] == 1, f"unread={threads[0]['unread']}")

    # 6. Менеджер читает → непрочитанных 0
    await crud.mark_chat_read_by_manager(user.id)
    threads = await crud.get_chat_threads()
    check("chat: после прочтения непрочитанных = 0", threads[0]["unread"] == 0)

    # 7. Менеджер отвечает → не прочитано клиентом
    m2 = await crud.add_chat_message(user.id, "manager", "Завтра отправим, трек пришлём", employee_id=None)
    check("chat: ответ менеджера не прочитан клиентом", not m2.is_read_by_client and m2.is_read_by_manager)

    # 8. История целиком и инкрементально
    msgs = await crud.get_chat_messages(user.id)
    check("chat: история из 2 сообщений в порядке", [m.sender for m in msgs] == ["client", "manager"])
    msgs_new = await crud.get_chat_messages(user.id, since_id=m1.id)
    check("chat: since_id возвращает только новые", len(msgs_new) == 1 and msgs_new[0].id == m2.id)

    # 9. Telegram-клиент: тот же чат через ensure_chat_token
    tg_user = await crud.get_or_create_user(555000111, "tg_client")
    tg_token = await crud.ensure_chat_token(tg_user.id)
    check("chat: TG-клиент получает chat_token", bool(tg_token))
    await crud.add_chat_message(tg_user.id, "client", "Вопрос из бота")
    threads = await crud.get_chat_threads()
    check("chat: второй диалог в тредах", len(threads) == 2, f"threads={len(threads)}")

    # 10. Клиент прочитал ответ менеджера
    await crud.mark_chat_read_by_client(user.id)
    msgs = await crud.get_chat_messages(user.id)
    check("chat: клиент прочитал ответ", all(m.is_read_by_client for m in msgs if m.sender == "manager"))

    failed = [r for r in RESULTS if not r[1]]
    print("\n=== ИТОГ ===")
    print(f"Пройдено: {len(RESULTS) - len(failed)} / {len(RESULTS)}")
    if failed:
        for name, _, detail in failed:
            print(f"  ❌ {name} {detail}")
        return 1
    print("✅ Все тесты чата пройдены")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
