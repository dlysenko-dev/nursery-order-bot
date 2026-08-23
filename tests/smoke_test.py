"""Комплексный дымовой тест бота. Запускать из корня проекта в venv."""
from __future__ import annotations

import ast
import asyncio
import os
import pathlib
import sqlite3
import sys
import tempfile
import traceback
from types import SimpleNamespace

# Переключаем stdout/stderr в UTF-8, чтобы emoji и русский текст выводились корректно
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Добавляем корень проекта в sys.path, чтобы импорты работали при запуске из tests/
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from typing import Any

# --- временная БД для тестов, чтобы не трогать plant_shop.db ---
original_db_url = os.environ.get("DATABASE_URL")
TEST_DB_PATH = pathlib.Path(tempfile.gettempdir()) / "nursery_bot_smoke_test.db"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

from config import (
    ADMIN_IDS,
    BOT_TOKEN,
    DATABASE_URL,
    DEFAULT_DELIVERY_COST,
    DEFAULT_PAYMENT_REQUISITES,
    DEFAULT_PICKUP_ADDRESS,
)


class SmokeResult:
    def __init__(self) -> None:
        self.ok: list[str] = []
        self.fail: list[str] = []
        self.info: list[str] = []

    def add(self, section: str, ok: bool, detail: str = "") -> None:
        msg = f"{'✅' if ok else '❌'} {section}" + (f" — {detail}" if detail else "")
        print(msg)
        (self.ok if ok else self.fail).append(msg)

    def summary(self) -> str:
        lines = ["", "=== ИТОГОВЫЙ ОТЧЁТ ==="]
        lines.append(f"Пройдено: {len(self.ok)}")
        lines.append(f"Ошибок: {len(self.fail)}")
        if self.fail:
            lines.extend(["", "❌ ОШИБКИ:"] + [f"  {x}" for x in self.fail])
        if self.info:
            lines.extend(["", "ℹ️ ПРИМЕЧАНИЯ:"] + [f"  {x}" for x in self.info])
        return "\n".join(lines)


RESULT = SmokeResult()


def _exc_detail() -> str:
    return traceback.format_exc().splitlines()[-1]


async def check_env_config() -> None:
    print("\n--- 1. Конфигурация и окружение ---")
    try:
        assert BOT_TOKEN, "BOT_TOKEN пустой"
        RESULT.add("BOT_TOKEN задан", True)
    except AssertionError as e:
        RESULT.add("BOT_TOKEN задан", False, str(e))

    try:
        assert isinstance(ADMIN_IDS, list), "ADMIN_IDS не список"
        assert all(isinstance(x, int) for x in ADMIN_IDS), "ADMIN_IDS содержит не int"
        RESULT.add("ADMIN_IDS корректен", True, f"{ADMIN_IDS}")
    except Exception:
        RESULT.add("ADMIN_IDS корректен", False, _exc_detail())

    try:
        assert DATABASE_URL.startswith("sqlite+aiosqlite:///"), f"DATABASE_URL: {DATABASE_URL}"
        RESULT.add("DATABASE_URL SQLite", True, DATABASE_URL)
    except Exception:
        RESULT.add("DATABASE_URL SQLite", False, _exc_detail())

    try:
        assert DEFAULT_DELIVERY_COST >= 0, "стоимость доставки"
        assert DEFAULT_PAYMENT_REQUISITES, "реквизиты не заданы"
        RESULT.add("Базовые настройки", True)
    except Exception:
        RESULT.add("Базовые настройки", False, _exc_detail())

    try:
        import aiogram, sqlalchemy, aiosqlite, dotenv, gspread, aiofiles
        RESULT.add("Зависимости импортируются", True,
                   f"aiogram {aiogram.__version__}, sqlalchemy {sqlalchemy.__version__}, aiosqlite {aiosqlite.__version__}")
    except Exception:
        RESULT.add("Зависимости импортируются", False, _exc_detail())


async def check_syntax_and_imports() -> None:
    print("\n--- 2. Статические и импорт-проверки ---")
    root = PROJECT_ROOT
    bad: list[str] = []
    for p in root.rglob("*.py"):
        if "venv" in p.parts or "__pycache__" in p.parts or p.name == "smoke_test.py":
            continue
        try:
            ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            bad.append(f"{p.relative_to(root)}: {exc}")
    if bad:
        RESULT.add("Синтаксис .py файлов", False, "; ".join(bad))
    else:
        RESULT.add("Синтаксис .py файлов", True)

    try:
        import bot
        assert len(bot.dp.sub_routers) == 14, f"роутеров: {len(bot.dp.sub_routers)}"
        RESULT.add("Импорт bot.py и роутеры", True, f"{len(bot.dp.sub_routers)} роутеров")
    except Exception:
        RESULT.add("Импорт bot.py и роутеры", False, _exc_detail())

    modules = [
        "handlers.start", "handlers.catalog", "handlers.cart", "handlers.checkout",
        "handlers.payment", "handlers.info",
        "handlers.admin.orders", "handlers.admin.payment_check", "handlers.admin.shipping",
        "handlers.admin.catalog_mgmt", "handlers.admin.settings",
        "services.calculator", "services.logger", "services.sheets",
        "db.database", "db.crud", "db.models",
        "keyboards.main_menu", "keyboards.catalog_kb", "keyboards.cart_kb",
        "keyboards.checkout_kb", "keyboards.admin_kb",
        "states.states",
    ]
    failed = []
    for mod in modules:
        try:
            __import__(mod)
        except Exception as exc:
            failed.append(f"{mod}: {exc}")
    if failed:
        RESULT.add("Импорт всех модулей", False, "; ".join(failed))
    else:
        RESULT.add("Импорт всех модулей", True, f"{len(modules)} модулей")


async def check_database() -> None:
    print("\n--- 3. База данных и схема ---")
    from db.database import engine, init_db
    from db.models import Base

    try:
        await init_db()
        RESULT.add("init_db()", True)
    except Exception:
        RESULT.add("init_db()", False, _exc_detail())
        return

    try:
        expected_tables = {
            "users", "categories", "catalog_items", "orders", "order_items",
            "payments", "event_logs", "settings",
        }
        # проверим через SQLAlchemy метаданные
        actual_tables = set(Base.metadata.tables.keys())
        assert expected_tables <= actual_tables, f"не хватает таблиц: {expected_tables - actual_tables}"
        RESULT.add("Таблицы созданы", True, f"{len(actual_tables)} таблиц")
    except Exception:
        RESULT.add("Таблицы созданы", False, _exc_detail())

    # Проверка целостности существующей plant_shop.db
    try:
        actual_db = pathlib.Path("plant_shop.db")
        if actual_db.exists():
            conn = sqlite3.connect(actual_db)
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cur.fetchall()}
            conn.close()
            expected = {"users", "categories", "catalog_items", "orders", "order_items", "payments", "event_logs", "settings"}
            if expected <= tables:
                RESULT.add("Целостность plant_shop.db", True, f"{len(tables)} таблиц")
            else:
                RESULT.add("Целостность plant_shop.db", False, f"нет таблиц: {expected - tables}")
        else:
            RESULT.add("Целостность plant_shop.db", False, "plant_shop.db не найдена")
    except Exception:
        RESULT.add("Целостность plant_shop.db", False, _exc_detail())

    await engine.dispose()


async def check_crud_and_logic() -> None:
    print("\n--- 4. CRUD-сценарий и бизнес-логика ---")
    from db.crud import (
        add_item_to_cart,
        create_catalog_item,
        create_category,
        get_or_create_draft,
        get_order_by_id,
        log_event,
        set_setting,
        update_order_status,
    )
    from db.models import OrderStatus

    try:
        cat = await create_category("Тестовая", "test_cat", 250.0, sort_order=99)
        item = await create_catalog_item("test_cat", photo_number=1, price=250.0, stock=10)
        order = await get_or_create_draft(telegram_id=123456, username="tester")
        await add_item_to_cart(order.id, item.id, quantity=3)
        order = await get_order_by_id(order.id)
        assert order is not None
        assert len(order.items) == 1
        assert order.plants_cost == 750.0, f"plants_cost={order.plants_cost}"
        assert order.total_cost == order.plants_cost + order.delivery_cost
        assert order.prepayment == order.total_cost  # полная предоплата 100%
        assert order.remainder == 0.0
        RESULT.add("Сценарий корзины/заказа", True, f"заказ №{order.id}, сумма {order.total_cost}")
    except Exception:
        RESULT.add("Сценарий корзины/заказа", False, _exc_detail())
        return

    try:
        await update_order_status(order.id, OrderStatus.AWAITING_PREPAYMENT)
        order2 = await get_order_by_id(order.id)
        assert order2.status == OrderStatus.AWAITING_PREPAYMENT
        await update_order_status(order.id, OrderStatus.PLACED)
        RESULT.add("Статусные переходы", True)
    except Exception:
        RESULT.add("Статусные переходы", False, _exc_detail())

    try:
        await log_event("smoke_test", user_telegram_id=123456, order_id=order.id, details="ok")
        RESULT.add("Логирование событий", True)
    except Exception:
        RESULT.add("Логирование событий", False, _exc_detail())

    try:
        await set_setting("smoke_key", "smoke_value")
        from db.crud import get_setting
        val = await get_setting("smoke_key")
        assert val == "smoke_value"
        RESULT.add("Настройки (get/set)", True)
    except Exception:
        RESULT.add("Настройки (get/set)", False, _exc_detail())


async def check_calculator() -> None:
    print("\n--- 5. Калькулятор ---")
    from services.calculator import calculate_order, format_order_summary

    try:
        calc = calculate_order(plants_cost=900, delivery_cost=300)
        assert calc.total == 1200
        assert calc.prepayment == 1200  # полная предоплата
        assert calc.remainder == 0
        text = format_order_summary(calc)
        assert "1200" in text and "Остаток" not in text
        RESULT.add("Расчёт предоплаты и форматирование", True)
    except Exception:
        RESULT.add("Расчёт предоплаты и форматирование", False, _exc_detail())


async def check_keyboards() -> None:
    print("\n--- 6. Клавиатуры ---")
    from keyboards.main_menu import main_menu_kb, back_to_menu_kb
    from keyboards.catalog_kb import category_list_kb, category_card_kb, photo_carousel_kb
    from keyboards.cart_kb import cart_kb, empty_cart_kb, cart_item_remove_kb
    from keyboards.checkout_kb import phone_request_kb, skip_comment_kb, order_preview_kb, template_kb
    from keyboards.admin_kb import admin_main_menu_kb, payment_check_kb, shipped_kb, admin_back_kb

    try:
        cat = SimpleNamespace(name="Пионы", slug="pion")
        oi = SimpleNamespace(
            id=1,
            catalog_item=SimpleNamespace(
                category=SimpleNamespace(name="Пионы"), photo_number=1
            ),
        )
        builders = [
            lambda: main_menu_kb(),
            lambda: main_menu_kb(has_draft=True),
            lambda: back_to_menu_kb(),
            lambda: category_list_kb([cat]),
            lambda: category_card_kb("pion"),
            lambda: photo_carousel_kb(0, 3, 1, "pion"),
            lambda: cart_kb(),
            lambda: empty_cart_kb(),
            lambda: cart_item_remove_kb([oi]),
            lambda: phone_request_kb(),
            lambda: skip_comment_kb(),
            lambda: order_preview_kb(),
            lambda: template_kb(),
            lambda: admin_main_menu_kb(),
            lambda: payment_check_kb(1),
            lambda: shipped_kb(1),
            lambda: admin_back_kb(),
        ]
        for fn in builders:
            kb = fn()
            assert kb is not None
        RESULT.add("Все клавиатуры собираются", True, f"{len(builders)} шт.")
    except Exception:
        RESULT.add("Все клавиатуры собираются", False, _exc_detail())


async def check_sheets() -> None:
    print("\n--- 7. Google Sheets (без credentials) ---")
    from services import sheets

    try:
        # Без GOOGLE_SHEETS_ID/_get_sheet должен вернуть None и не упасть
        sheet = sheets._get_sheet()
        assert sheet is None, f"ожидали None, получили {sheet}"
        RESULT.add("Инициализация Sheets без credentials", True, "возвращает None")
    except Exception:
        RESULT.add("Инициализация Sheets без credentials", False, _exc_detail())
        return

    try:
        # Фейковый заказ для save_order_to_sheets — должно отработать без ошибок, ничего не записав
        order = SimpleNamespace(
            id=999,
            created_at=SimpleNamespace(date=lambda: "2024-01-01", time=lambda: SimpleNamespace(strftime=lambda fmt: "12:00")),
            user=SimpleNamespace(telegram_id=123456, username="test"),
            full_name="Test",
            phone="+79990000000",
            city="City",
            pickup_point="point",
            comment="",
            plants_cost=100.0,
            delivery_cost=300.0,
            total_cost=400.0,
            prepayment=120.0,
            remainder=280.0,
            receipt_file_id="",
            status=SimpleNamespace(value="Оформлен"),
            track_number="",
            items=[
                SimpleNamespace(
                    quantity=1,
                    price_at_order=100.0,
                    catalog_item=SimpleNamespace(
                        category=SimpleNamespace(name="Пионы"),
                        photo_number=1,
                    ),
                )
            ],
        )
        await sheets.save_order_to_sheets(order)
        RESULT.add("Сохранение заказа в Sheets (offline)", True, "без credentials не падает")
    except Exception:
        RESULT.add("Сохранение заказа в Sheets (offline)", False, _exc_detail())


async def check_full_order_cycle() -> None:
    print("\n--- 8. Полный цикл заказа (остатки, чек, отмена) ---")
    from db.crud import (
        add_item_to_cart,
        check_order_stock,
        create_catalog_item,
        create_category,
        get_active_order,
        get_item_by_id,
        get_or_create_draft,
        get_order_by_id,
        reserve_stock_for_order,
        restore_stock_for_order,
        save_customer_data,
        save_receipt,
        update_order_status,
    )
    from db.models import OrderStatus

    try:
        await create_category("Цикл", "cycle_cat", 100.0, sort_order=98)
        item = await create_catalog_item("cycle_cat", photo_number=1, price=100.0, stock=3)
        order = await get_or_create_draft(telegram_id=777001, username="cycle_tester")

        # 1. В корзину нельзя добавить больше остатка (3 шт.)
        added = await add_item_to_cart(order.id, item.id, 5)
        assert added == 3, f"добавлено {added}, ожидали 3"
        added2 = await add_item_to_cart(order.id, item.id, 1)
        assert added2 == 0, f"повторно добавлено {added2}, ожидали 0"
        RESULT.add("Корзина: лимит по остатку", True)
    except Exception:
        RESULT.add("Корзина: лимит по остатку", False, _exc_detail())
        return

    try:
        # 2. Проверка остатков и списание при подтверждении
        assert await check_order_stock(order.id) == []
        await save_customer_data(order.id, "Тест", "+7000", "Город", "Пункт", None)
        await reserve_stock_for_order(order.id)
        await update_order_status(order.id, OrderStatus.AWAITING_PREPAYMENT)
        item_after = await get_item_by_id(item.id)
        assert item_after.stock == 0, f"остаток {item_after.stock}, ожидали 0"
        RESULT.add("Списание остатков при заказе", True)
    except Exception:
        RESULT.add("Списание остатков при заказе", False, _exc_detail())
        return

    try:
        # 3. Активный заказ находится (сценарий повторной отправки чека)
        active = await get_active_order(777001)
        assert active and active.id == order.id, "активный заказ не найден"
        await save_receipt(order.id, "file_id_receipt")
        order2 = await get_order_by_id(order.id)
        assert order2.status == OrderStatus.ON_REVIEW
        # имитация отклонения -> заказ снова ждёт предоплату -> снова активен для чека
        await update_order_status(order.id, OrderStatus.AWAITING_PREPAYMENT)
        active2 = await get_active_order(777001)
        assert active2 and active2.status == OrderStatus.AWAITING_PREPAYMENT
        RESULT.add("Повторная отправка чека (активный заказ)", True)
    except Exception:
        RESULT.add("Повторная отправка чека (активный заказ)", False, _exc_detail())
        return

    try:
        # 4. Отмена заказа возвращает остатки
        await restore_stock_for_order(order.id)
        await update_order_status(order.id, OrderStatus.CANCELLED)
        item_restored = await get_item_by_id(item.id)
        assert item_restored.stock == 3, f"остаток {item_restored.stock}, ожидали 3"
        RESULT.add("Возврат остатков при отмене", True)
    except Exception:
        RESULT.add("Возврат остатков при отмене", False, _exc_detail())


async def check_new_features() -> None:
    print("\n--- 9. Новые функции (саженцы, профиль, история, Excel) ---")
    from db.crud import (
        create_catalog_item,
        get_category_items,
        get_user_by_telegram_id,
        get_user_orders,
        save_user_contact_data,
    )
    from db.database import AsyncSessionLocal
    from db.models import CatalogItem

    try:
        item_s = await create_catalog_item("cycle_cat", photo_number=2, price=100.0, stock=5)
        assert item_s.kind == "product"
        async with AsyncSessionLocal() as s:
            it = await s.get(CatalogItem, item_s.id)
            it.kind = "sapling"
            await s.commit()
        products = await get_category_items("cycle_cat", kind="product")
        saplings = await get_category_items("cycle_cat", kind="sapling")
        assert len(saplings) == 1 and all(i.kind == "product" for i in products)
        RESULT.add("Фильтр позиций по kind (саженцы)", True)
    except Exception:
        RESULT.add("Фильтр позиций по kind (саженцы)", False, _exc_detail())

    try:
        await save_user_contact_data(777001, "Иван Тестов", "+70001112233", "Город", "ПВЗ-1")
        u = await get_user_by_telegram_id(777001)
        assert u.full_name == "Иван Тестов" and u.pickup_point == "ПВЗ-1"
        RESULT.add("Профиль клиента («как в прошлый раз»)", True)
    except Exception:
        RESULT.add("Профиль клиента («как в прошлый раз»)", False, _exc_detail())

    try:
        orders = await get_user_orders(777001)
        assert orders, "история пуста"
        RESULT.add("История заказов пользователя", True, f"{len(orders)} заказ(а)")
    except Exception:
        RESULT.add("История заказов пользователя", False, _exc_detail())

    try:
        from services.export import build_export_xlsx
        data = await build_export_xlsx()
        assert data[:2] == b"PK" and len(data) > 1000, f"подозрительный размер: {len(data)}"
        RESULT.add("Сборка Excel-выгрузки", True, f"{len(data)} байт")
    except Exception:
        RESULT.add("Сборка Excel-выгрузки", False, _exc_detail())


async def check_media_and_content() -> None:
    print("\n--- 8. Медиа и контент ---")
    media_dir = pathlib.Path("media/category_images")
    try:
        files = list(media_dir.glob("*")) if media_dir.exists() else []
        if files:
            RESULT.add("Медиа-файлы категорий", True, f"{len(files)} файлов")
        else:
            RESULT.add("Медиа-файлы категорий", False, "директория пуста или не найдена")
    except Exception:
        RESULT.add("Медиа-файлы категорий", False, _exc_detail())

    try:
        from data.faq import FAQ_ITEMS
        assert len(FAQ_ITEMS) > 0
        for item in FAQ_ITEMS:
            assert item["question"] and item["answer"]
        RESULT.add("FAQ-контент", True, f"{len(FAQ_ITEMS)} пунктов")
    except Exception:
        RESULT.add("FAQ-контент", False, _exc_detail())


async def check_telegram_live() -> None:
    print("\n--- 9. Живая проверка Telegram ---")
    if not BOT_TOKEN:
        RESULT.add("Telegram getMe", False, "BOT_TOKEN отсутствует")
        return

    from aiogram import Bot
    from aiogram.exceptions import TelegramConflictError

    try:
        bot = Bot(token=BOT_TOKEN)
        me = await bot.get_me()
        RESULT.add("Telegram getMe", True, f"@{me.username} (id={me.id})")
    except Exception as exc:
        RESULT.add("Telegram getMe", False, f"{type(exc).__name__}: {exc}")
        return
    finally:
        try:
            await bot.session.close()
        except Exception:
            pass

    try:
        bot = Bot(token=BOT_TOKEN)
        await bot.delete_webhook(drop_pending_updates=True)
        from bot import dp, init_db

        async def _stop_later() -> None:
            await asyncio.sleep(10)
            await dp.stop_polling()

        await init_db()
        stop_task = asyncio.create_task(_stop_later())
        try:
            await dp.start_polling(bot, allowed_updates=[], polling_timeout=5)
        finally:
            if not stop_task.done():
                stop_task.cancel()
            await bot.session.close()
        RESULT.add("Короткий запуск polling", True, "10 секунд, allowed_updates=[]")
    except TelegramConflictError as exc:
        RESULT.add("Короткий запуск polling", False, f"Конфликт getUpdates: {exc}")
    except Exception as exc:
        RESULT.add("Короткий запуск polling", False, f"{type(exc).__name__}: {exc}")


async def main() -> None:
    print("Начинаю дымовое тестирование бота...")
    print(f"Временная тестовая БД: {DATABASE_URL}")
    await check_env_config()
    await check_syntax_and_imports()
    await check_database()
    await check_crud_and_logic()
    await check_calculator()
    await check_keyboards()
    await check_sheets()
    await check_full_order_cycle()
    await check_new_features()
    await check_media_and_content()
    await check_telegram_live()
    print(RESULT.summary())
    if RESULT.fail:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()
