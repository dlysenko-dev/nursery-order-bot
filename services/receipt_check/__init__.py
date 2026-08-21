"""Автоматическая проверка чеков об оплате: извлечение текста, разбор, сверка с заказом."""
from services.receipt_check.extract import extract_text
from services.receipt_check.parse import ParsedReceipt, parse_receipt
from services.receipt_check.verify import Verdict, verify_receipt
from services.receipt_check.pipeline import process_receipt

__all__ = [
    "extract_text",
    "ParsedReceipt",
    "parse_receipt",
    "Verdict",
    "verify_receipt",
    "process_receipt",
]
