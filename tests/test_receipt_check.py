"""Тесты автопроверки чеков: разбор текста, сверка, полный пайплайн с БД.

Запуск из корня проекта: python tests/test_receipt_check.py
Образцы чеков — синтетические (Сбер, Т-Банк, Ozon), повторяющие реальную вёрстку.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal

# UTF-8 для русского текста в консоли Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Временная БД до импорта db — engine создаётся при импорте из DATABASE_URL
TEST_DB_PATH = pathlib.Path(tempfile.gettempdir()) / "nursery_receipt_test.db"
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

from db.database import init_db  # noqa: E402
from db import crud  # noqa: E402
from db.models import OrderStatus  # noqa: E402
from services.receipt_check import parse_receipt, verify_receipt, process_receipt  # noqa: E402
from services.receipt_check.pipeline import (  # noqa: E402
    STATUS_AUTO_APPROVED,
    STATUS_NEEDS_REVIEW,
    STATUS_REJECTED,
)

REQUISITES = {
    "card": "2202 2032 1234 5678",
    "phone_sbp": "+7 923 398-19-17",
    "wallet": "",
    "recipient_name": "Лысенко Дмитрий",
    "fallback_text": "Ozon Банк: 89233981917",
}

NOW = datetime.utcnow()
DATE_STR = NOW.strftime("%d.%m.%Y %H:%M")

# --- Образцы чеков (моноширинная вёрстка банковских PDF) ---

SBER_RECEIPT = f"""
Сбербанк Онлайн
Перевод по номеру карты
Получатель: Лысенко Дмитрий Сергеевич
Карта получателя: **** **** **** 5678
Сумма перевода: 1 500,00 ₽
Дата операции: {DATE_STR}
Номер операции: SBOL-84729105
Операция выполнена успешно
"""

TBANK_RECEIPT = f"""
Т-Банк
Перевод по СБП
Кому: Лысенко Д.
Телефон получателя: +7 (923) 398-19-17
Сумма: 1 500,00 руб
Дата: {DATE_STR}
Идентификатор операции: T7120039845
Статус: Исполнено
"""

OZON_RECEIPT = f"""
Ozon Банк
Перевод по номеру телефона
Получатель — Лысенко Дмитрий
Оплата: 1500 руб.
{NOW.strftime("%d.%m.%Y")} в {NOW.strftime("%H:%M")}
Документ № 402288173
"""

WRONG_AMOUNT = SBER_RECEIPT.replace("1 500,00", "1 000,00")
OLD_DATE = SBER_RECEIPT.replace(DATE_STR, (NOW - timedelta(hours=72)).strftime("%d.%m.%Y %H:%M"))
WRONG_RECIPIENT = (SBER_RECEIPT.replace("Лысенко Дмитрий Сергеевич", "Иванова Анна Петровна")
                   .replace("5678", "9999").replace("SBOL-84729105", "SBOL-55555555"))

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    RESULTS.append((name, condition, detail))
    print(f"{'✅' if condition else '❌'} {name}" + (f" — {detail}" if detail else ""))


def test_parse() -> None:
    p = parse_receipt(SBER_RECEIPT)
    check("parse: Сбер — сумма", p.amount == Decimal("1500.00"), f"amount={p.amount}")
    check("parse: Сбер — получатель (ФИО)", p.recipient is not None and "Лысенко" in p.recipient, f"recipient={p.recipient}")
    check("parse: Сбер — номер операции", p.operation_id == "SBOL-84729105", f"op={p.operation_id}")
    check("parse: Сбер — банк", p.bank_hint == "Сбербанк")
    check("parse: Сбер — дата", p.paid_at is not None and abs((p.paid_at - NOW).total_seconds()) < 120, f"paid_at={p.paid_at}")

    p = parse_receipt(TBANK_RECEIPT)
    check("parse: Т-Банк — сумма", p.amount == Decimal("1500.00"), f"amount={p.amount}")
    check("parse: Т-Банк — телефон получателя", p.recipient is not None and "923" in p.recipient, f"recipient={p.recipient}")
    check("parse: Т-Банк — номер операции", p.operation_id == "T7120039845", f"op={p.operation_id}")

    p = parse_receipt(OZON_RECEIPT)
    check("parse: Ozon — сумма", p.amount == Decimal("1500.00"), f"amount={p.amount}")
    check("parse: Ozon — получатель", p.recipient is not None and "Лысенко" in p.recipient, f"recipient={p.recipient}")
    check("parse: Ozon — номер документа", p.operation_id == "402288173", f"op={p.operation_id}")

    p = parse_receipt("")
    check("parse: пустой текст → пустой результат", p.amount is None and p.recipient is None)


def test_verify() -> None:
    p = parse_receipt(SBER_RECEIPT)
    v = verify_receipt(p, 1500.0, REQUISITES, now=NOW)
    check("verify: идеальный чек → ok, без сомнений", v.ok and not v.reasons, f"reasons={v.reasons}")

    p = parse_receipt(WRONG_AMOUNT)
    v = verify_receipt(p, 1500.0, REQUISITES, now=NOW)
    check("verify: другая сумма → жёсткий отказ", not v.ok and any("не совпадает" in r for r in v.reasons))

    p = parse_receipt(OLD_DATE)
    v = verify_receipt(p, 1500.0, REQUISITES, now=NOW)
    check("verify: чек старше 48ч → жёсткий отказ", not v.ok and any("старый" in r for r in v.reasons))

    p = parse_receipt(WRONG_RECIPIENT)
    v = verify_receipt(p, 1500.0, REQUISITES, now=NOW)
    check("verify: чужой получатель → жёсткий отказ", not v.ok and any("Получатель" in r for r in v.reasons))

    # Совпадение по телефону СБП (10 цифр без кода страны)
    p = parse_receipt(TBANK_RECEIPT)
    v = verify_receipt(p, 1500.0, REQUISITES, now=NOW)
    check("verify: Т-Банк СБП по телефону → ok", v.ok and not v.reasons, f"reasons={v.reasons}")


async def test_pipeline() -> None:
    await init_db()
    await crud.set_setting("payment_card", REQUISITES["card"])
    await crud.set_setting("payment_phone_sbp", REQUISITES["phone_sbp"])
    await crud.set_setting("payment_recipient_name", REQUISITES["recipient_name"])

    # Заказ на 5300 ₽ (5000 + доставка 300): полная предоплата 5300, остаток 0
    user = await crud.get_or_create_site_user("+79000000000", "Тестовый Клиент", source="site")
    category = (await crud.get_categories(active_only=False))[0]
    from db.models import CatalogItem
    from db.database import AsyncSessionLocal
    async with AsyncSessionLocal() as s:
        item = CatalogItem(category_id=category.id, photo_number=999001, title="Тест", price=5000.0, stock=10)
        s.add(item)
        await s.commit()
        await s.refresh(item)
        item_id = item.id

    order, problems = await crud.create_web_order(
        user_id=user.id,
        items=[{"item_id": item_id, "quantity": 1}],
        full_name="Тестовый Клиент", phone="+79000000000",
        city="Тест", pickup_point="5Post Тест",
        comment=None, source="site",
    )
    check("pipeline: заказ создан", order is not None and not problems, f"problems={problems}")
    order_id = order.id
    check("pipeline: pay_token сгенерирован", bool(order.pay_token))
    check("pipeline: предоплата 100%", order.prepayment == 5300.0, f"prepayment={order.prepayment}")

    def rub(amount: float) -> str:
        return f"{amount:,.2f}".replace(",", " ").replace(".", ",")  # 1590.0 → «1 590,00»

    prepay_receipt = SBER_RECEIPT.replace("1 500,00", rub(order.prepayment))

    # 1. Идеальный чек → авто-подтверждение
    payment, verdict = await process_receipt(
        prepay_receipt.encode("utf-8"), "receipt.txt", order, "prepayment", REQUISITES,
    )
    check("pipeline: идеальный чек → auto_approved", payment.check_status == STATUS_AUTO_APPROVED, f"reasons={verdict.reasons}")
    await crud.set_order_paid(order_id, "prepayment", payment.paid_at)
    order = await crud.get_order_by_id(order_id)
    check("pipeline: prepayment_paid_at проставлен", order.prepayment_paid_at is not None)

    # 2. Тот же файл повторно → отклонён как дубликат
    payment2, verdict2 = await process_receipt(
        prepay_receipt.encode("utf-8"), "receipt.txt", order, "prepayment", REQUISITES,
    )
    check("pipeline: повтор файла → rejected (анти-повтор по хешу)", payment2.check_status == STATUS_REJECTED)

    # 3. Та же операция другим файлом → отклонён (анти-повтор по номеру операции)
    same_op = prepay_receipt.replace("Перевод по номеру карты", "Перевод по номеру карты ")
    payment3, _ = await process_receipt(
        same_op.encode("utf-8"), "receipt_copy.txt", order, "prepayment", REQUISITES,
    )
    check("pipeline: тот же № операции → rejected", payment3.check_status == STATUS_REJECTED)

    # 4. Чужой получатель → ручная проверка с причиной
    payment4, verdict4 = await process_receipt(
        WRONG_RECIPIENT.encode("utf-8"), "wrong.txt", order, "prepayment", REQUISITES,
    )
    check(
        "pipeline: чужой получатель → needs_review с причиной",
        payment4.check_status == STATUS_NEEDS_REVIEW and any("Получатель" in r for r in verdict4.reasons),
        f"reasons={verdict4.reasons}",
    )

    # 5. Нечитаемый файл → needs_review «не удалось распознать»
    payment5, verdict5 = await process_receipt(
        b"\x00\x01\x02not-a-receipt", "broken.bin", order, "prepayment", REQUISITES,
    )
    check("pipeline: нечитаемый файл → needs_review", payment5.check_status == STATUS_NEEDS_REVIEW)

    # 6. Полная предоплата: остаток всегда 0, вторая стадия оплаты не нужна
    order = await crud.get_order_by_id(order_id)
    check("pipeline: остаток равен 0 (полная предоплата)", order.remainder == 0.0, f"remainder={order.remainder}")

    # 7. Поиск заказа по pay_token (страница /pay)
    found = await crud.get_order_by_pay_token(order.pay_token)
    check("pipeline: заказ находится по pay_token", found is not None and found.id == order_id)

    # 8. Ручное подтверждение админом: needs_review-платёж → verified + paid_at в заказе
    # (регрессия: confirm_payment раньше не проставлял paid_at и падал на заказах с сайта)
    order2, _ = await crud.create_web_order(
        user_id=user.id,
        items=[{"item_id": item_id, "quantity": 1}],
        full_name="Тестовый Клиент", phone="+79000000000",
        city="Тест", pickup_point="5Post Тест",
        comment=None, source="site",
    )
    manual_receipt = WRONG_RECIPIENT.replace("SBOL-55555555", "SBOL-77777777").replace("1 500,00", rub(order2.prepayment))
    payment_m, _ = await process_receipt(
        manual_receipt.encode("utf-8"), "manual.txt", order2, "prepayment", REQUISITES,
    )
    assert payment_m.check_status == STATUS_NEEDS_REVIEW
    approved = await crud.approve_payment_for_order(order2.id)
    order2 = await crud.get_order_by_id(order2.id)
    check(
        "pipeline: ручное подтверждение → verified + prepayment_paid_at",
        approved is not None and approved.verified and order2.prepayment_paid_at is not None,
    )


async def main() -> int:
    test_parse()
    test_verify()
    await test_pipeline()

    failed = [r for r in RESULTS if not r[1]]
    print("\n=== ИТОГ ===")
    print(f"Пройдено: {len(RESULTS) - len(failed)} / {len(RESULTS)}")
    if failed:
        print("❌ Провалы:")
        for name, _, detail in failed:
            print(f"  {name} {detail}")
        return 1
    print("✅ Все тесты автопроверки чеков пройдены")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
