"""Разбор текста чека: сумма, дата, получатель, номер операции.

Регулярки банк-независимые (Сбер, Т-Банк, Озон-банк, ВТБ и др.) — с общим fallback.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation


@dataclass
class ParsedReceipt:
    amount: Decimal | None = None
    paid_at: datetime | None = None
    recipient: str | None = None
    operation_id: str | None = None
    bank_hint: str | None = None


# --- Сумма: «1 234,56 ₽», «Сумма: 1234.56 руб», «Перевод 1 234 RUB» ---
_AMOUNT_RE = re.compile(
    r"(?:сумма|перевод|оплата|к\s*оплате|итого)?\s*[:№-]*\s*"
    r"(\d{1,3}(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
    r"\s*(?:₽|руб(?:\.|лей|ля)?|RUB|RUR)\b",
    re.IGNORECASE,
)
# --- Дата/время: 21.08.2026, 21.08.2026 14:35, 21.08.2026 в 14:35:01 ---
_DATE_RE = re.compile(
    r"\b(\d{2})[.](\d{2})[.](\d{4})(?:\s*(?:в\s*)?(\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?)?\b"
)
# --- Номер операции ---
_OPERATION_RE = re.compile(
    r"(?:№\s*операции|номер\s+операции|операция\s*№|operation\s*(?:id|№|number)?|"
    r"идентификатор\s*(?:операции|платежа)?|id\s*операции|номер\s+документа|документ\s*№)"
    r"\s*[:№-]*\s*([A-Za-zА-Яа-я0-9-]{4,})",
    re.IGNORECASE,
)
# --- Получатель ---
_CARD_RE = re.compile(r"\b(\d{4}[ \-]?\d{4}[ \-]?\d{4}[ \-]?\d{4})\b")
_MASKED_CARD_RE = re.compile(r"(?:\*{2,}|•{2,}|x{2,}|XXXX)?\s?\*?\s?(\d{4})\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\d)(\+7|8)([\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})(?!\d)")
_RECIPIENT_LINE_RE = re.compile(
    r"(?:получатель|перевод\s+(?:кому|на\s+имя)|кому|в\s+пользу|beneficiary)\s*[:—-]\s*(.+)",
    re.IGNORECASE,
)
_FIO_RE = re.compile(r"\b([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2})\b")

_BANK_HINTS = (
    ("сбер", "Сбербанк"),
    ("sber", "Сбербанк"),
    ("т-банк", "Т-Банк"),
    ("тбанк", "Т-Банк"),
    ("tinkoff", "Т-Банк"),
    ("тинькофф", "Т-Банк"),
    ("озон", "Ozon Банк"),
    ("ozon", "Ozon Банк"),
    ("втб", "ВТБ"),
    ("vtb", "ВТБ"),
    ("альфа", "Альфа-Банк"),
    ("alfa", "Альфа-Банк"),
)


def _parse_amount(raw: str) -> Decimal | None:
    cleaned = re.sub(r"[ \u00a0\u202f]", "", raw).replace(",", ".")
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def parse_receipt(text: str) -> ParsedReceipt:
    """Извлекает структурированные данные из текста чека. Пустой текст → пустой результат."""
    result = ParsedReceipt()
    if not text or not text.strip():
        return result
    lowered = text.lower()
    for marker, hint in _BANK_HINTS:
        if marker in lowered:
            result.bank_hint = hint
            break
    result.amount = _extract_amount(text)
    result.paid_at = _extract_date(text)
    result.operation_id = _extract_operation_id(text)
    result.recipient = _extract_recipient(text)
    return result


def _extract_amount(text: str) -> Decimal | None:
    # Приоритет — строки с явной подписью «сумма/перевод/оплата»
    labeled = re.compile(
        r"(?:сумма|перевод|оплата|к\s*оплате|итого)[^\d]{0,20}"
        r"(\d{1,3}(?:[ \u00a0\u202f]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
        r"\s*(?:₽|руб(?:\.|лей|ля)?|RUB|RUR)\b",
        re.IGNORECASE,
    )
    for pattern in (labeled, _AMOUNT_RE):
        amounts = []
        for m in pattern.finditer(text):
            value = _parse_amount(m.group(1))
            if value is not None and value > 0:
                amounts.append(value)
        if amounts:
            return max(amounts)  # в чеке обычно встречается и комиссия — берём наибольшую
    return None


def _extract_date(text: str) -> datetime | None:
    for m in _DATE_RE.finditer(text):
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hour = int(m.group(4)) if m.group(4) else 0
        minute = int(m.group(5)) if m.group(5) else 0
        second = int(m.group(6)) if m.group(6) else 0
        try:
            return datetime(year, month, day, hour, minute, second)
        except ValueError:
            continue
    return None


def _extract_operation_id(text: str) -> str | None:
    m = _OPERATION_RE.search(text)
    return m.group(1) if m else None


def _extract_recipient(text: str) -> str | None:
    # Явная строка «Получатель: ...»
    m = _RECIPIENT_LINE_RE.search(text)
    if m:
        candidate = m.group(1).strip()
        if candidate:
            return candidate
    # Полный номер карты 4x4
    m = _CARD_RE.search(text)
    if m:
        return m.group(1)
    # Телефон +7/8
    m = _PHONE_RE.search(text)
    if m:
        return m.group(0)
    # Маскированная карта *1234
    m = _MASKED_CARD_RE.search(text)
    if m:
        return f"*{m.group(1)}"
    # ФИО кириллицей (2–3 слова с заглавной)
    m = _FIO_RE.search(text)
    if m:
        return m.group(1)
    return None
