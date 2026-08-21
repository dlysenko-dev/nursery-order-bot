"""Пайплайн автопроверки чека: хеш → анти-повтор → извлечение текста → разбор → сверка → Payment."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal

from db import crud
from db.models import Order, Payment
from services.receipt_check.extract import extract_text
from services.receipt_check.parse import parse_receipt
from services.receipt_check.verify import Verdict, verify_receipt

logger = logging.getLogger(__name__)

# Возможные значения check_status платежа
STATUS_AUTO_APPROVED = "auto_approved"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_REJECTED = "rejected"


def expected_amount(order: Order, kind: str) -> float:
    """Сколько клиент должен оплатить сейчас: предоплата или остаток."""
    return order.prepayment if kind == "prepayment" else order.remainder


def _json_default(value):
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


async def process_receipt(
    file_bytes: bytes,
    filename: str,
    order: Order,
    kind: str,
    requisites: dict,
    receipt_file_id: str | None = None,
) -> tuple[Payment, Verdict]:
    """Полный цикл проверки чека. Создаёт запись Payment с результатом и возвращает (payment, verdict)."""
    receipt_hash = hashlib.sha256(file_bytes).hexdigest()
    amount = expected_amount(order, kind)

    # Анти-повтор по файлу: такой чек уже подтверждали
    seen = await crud.is_receipt_seen(receipt_hash, None)
    if seen:
        verdict = Verdict(ok=False, reasons=[f"Такой чек уже использовался для оплаты заказа №{seen.order_id}"])
        payment = await crud.create_payment(
            order_id=order.id, amount=amount, kind=kind,
            receipt_file_id=receipt_file_id, receipt_hash=receipt_hash,
            check_status=STATUS_REJECTED,
            check_details=json.dumps({"reasons": verdict.reasons}, ensure_ascii=False),
        )
        return payment, verdict

    text = extract_text(file_bytes, filename)
    if not text.strip():
        verdict = Verdict(ok=False, reasons=["Не удалось распознать текст чека (нужна проверка вручную)"])
        payment = await crud.create_payment(
            order_id=order.id, amount=amount, kind=kind,
            receipt_file_id=receipt_file_id, receipt_hash=receipt_hash,
            check_status=STATUS_NEEDS_REVIEW,
            check_details=json.dumps({"reasons": verdict.reasons}, ensure_ascii=False),
        )
        return payment, verdict

    parsed = parse_receipt(text)

    # Анти-повтор по номеру операции: та же операция уже подтверждалась
    if parsed.operation_id:
        seen = await crud.is_receipt_seen(None, parsed.operation_id)
        if seen:
            verdict = Verdict(ok=False, reasons=[f"Операция №{parsed.operation_id} уже подтверждалась по заказу №{seen.order_id}"])
            payment = await crud.create_payment(
                order_id=order.id, amount=amount, kind=kind,
                receipt_file_id=receipt_file_id, receipt_hash=receipt_hash,
                operation_id=parsed.operation_id, paid_at=parsed.paid_at,
                check_status=STATUS_REJECTED,
                check_details=json.dumps({"parsed": asdict(parsed), "reasons": verdict.reasons}, ensure_ascii=False, default=_json_default),
            )
            return payment, verdict

    verdict = verify_receipt(parsed, amount, requisites, now=datetime.utcnow())
    # Автоподтверждение — только при полном совпадении (нет ни ошибок, ни сомнений)
    auto = verdict.ok and not verdict.reasons
    payment = await crud.create_payment(
        order_id=order.id, amount=amount, kind=kind,
        receipt_file_id=receipt_file_id, receipt_hash=receipt_hash,
        operation_id=parsed.operation_id, paid_at=parsed.paid_at,
        check_status=STATUS_AUTO_APPROVED if auto else STATUS_NEEDS_REVIEW,
        check_details=json.dumps({"parsed": asdict(parsed), "ok": verdict.ok, "reasons": verdict.reasons}, ensure_ascii=False, default=_json_default),
    )
    return payment, verdict
