"""Сверка распознанного чека с заказом и реквизитами питомника.

ok=False — есть жёсткое несоответствие (сумма, дата, получатель).
reasons — мягкие сомнения (не распознана дата/получатель/номер операции).
Автоподтверждение — только когда ok=True и reasons пуст (полное совпадение).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from services.receipt_check.parse import ParsedReceipt

AMOUNT_TOLERANCE = Decimal("1")  # допуск по сумме, ₽
MAX_AGE = timedelta(hours=48)  # чек не старше 48 часов
MAX_FUTURE = timedelta(minutes=15)  # чек не «из будущего»


@dataclass
class Verdict:
    ok: bool
    reasons: list[str] = field(default_factory=list)


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _normalize_phone(digits: str) -> str:
    """Последние 10 цифр — сравнение телефонов без кода страны (+7/8)."""
    return digits[-10:] if len(digits) >= 10 else digits


def _recipient_matches(recipient: str, requisites: dict) -> bool:
    """Совпадает ли получатель чека с одним из текущих реквизитов."""
    rec_digits = _digits(recipient)
    rec_text = recipient.lower()
    # Карта / кошелёк: сравнение по последним 4 цифрам
    for key in ("card", "wallet"):
        req_digits = _digits(requisites.get(key) or "")
        if req_digits and rec_digits and req_digits[-4:] == rec_digits[-4:]:
            return True
    # Телефон СБП: сравнение по 10 цифрам
    req_phone = _digits(requisites.get("phone_sbp") or "")
    if req_phone and rec_digits and _normalize_phone(req_phone) == _normalize_phone(rec_digits):
        return True
    # ФИО получателя: все слова из настроек должны встретиться в чеке (или наоборот)
    req_name = (requisites.get("recipient_name") or "").lower().strip()
    if req_name:
        req_words = {w for w in re.split(r"\s+", req_name) if len(w) > 2}
        rec_words = {w for w in re.split(r"\s+", rec_text) if len(w) > 2}
        if req_words and (req_words <= rec_words or rec_words <= req_words) and req_words & rec_words:
            return True
    # Fallback-текст реквизитов: совпадение по цифрам (телефон/карта внутри текста)
    fallback_digits = _digits(requisites.get("fallback_text") or "")
    if fallback_digits and rec_digits and (
        _normalize_phone(fallback_digits) == _normalize_phone(rec_digits)
        or fallback_digits[-4:] == rec_digits[-4:]
    ):
        return True
    return False


def verify_receipt(
    parsed: ParsedReceipt,
    order_amount: float | Decimal,
    requisites: dict,
    now: datetime,
) -> Verdict:
    """Проверяет чек по правилам: сумма, дата, получатель, номер операции."""
    reasons: list[str] = []
    hard_fail = False
    expected = Decimal(str(order_amount)).quantize(Decimal("0.01"))

    # Сумма
    if parsed.amount is None:
        reasons.append("Не удалось распознать сумму в чеке")
    elif abs(parsed.amount - expected) > AMOUNT_TOLERANCE:
        hard_fail = True
        reasons.append(f"Сумма в чеке {parsed.amount} ₽ не совпадает с требуемой {expected} ₽")

    # Дата оплаты
    if parsed.paid_at is None:
        reasons.append("Не удалось распознать дату оплаты")
    elif parsed.paid_at < now - MAX_AGE:
        hard_fail = True
        reasons.append(f"Чек слишком старый ({parsed.paid_at:%d.%m.%Y %H:%M}), оплата старше 48 часов")
    elif parsed.paid_at > now + MAX_FUTURE:
        hard_fail = True
        reasons.append(f"Дата чека из будущего ({parsed.paid_at:%d.%m.%Y %H:%M})")

    # Получатель
    if parsed.recipient is None:
        reasons.append("Не удалось распознать получателя платежа")
    elif not _recipient_matches(parsed.recipient, requisites):
        hard_fail = True
        reasons.append(f"Получатель «{parsed.recipient}» не совпадает с реквизитами питомника")

    # Номер операции — желателен (для анти-повтора), но не обязателен
    if not parsed.operation_id:
        reasons.append("Не удалось распознать номер операции")

    return Verdict(ok=not hard_fail, reasons=reasons)
