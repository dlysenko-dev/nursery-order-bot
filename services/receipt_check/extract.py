"""Извлечение текста из чека: PDF — через pdfplumber, изображения — через pytesseract (OCR).

Если OCR недоступен (нет бинарника tesseract и т.п.) — возвращаем пустую строку:
пайплайн отправит такой чек админу как «нечитаемый».
"""
from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff")


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Возвращает текст чека или пустую строку, если распознать не удалось."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return _extract_pdf(file_bytes)
    # Telegram-фото приходят без имени — считаем их изображениями
    if not name or name.endswith(_IMAGE_EXTENSIONS):
        return _extract_image(file_bytes)
    # Неизвестный формат: пробуем как изображение, потом как PDF
    text = _extract_image(file_bytes)
    return text if text else _extract_pdf(file_bytes)


def _extract_pdf(file_bytes: bytes) -> str:
    try:
        import pdfplumber

        parts: list[str] = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
        return "\n".join(parts).strip()
    except Exception as exc:
        logger.warning("Не удалось извлечь текст из PDF-чека: %s", exc)
        return ""


def _extract_image(file_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
    except Exception as exc:
        logger.warning("OCR-библиотеки недоступны (%s) — чек уйдёт на ручную проверку", exc)
        return ""
    try:
        image = Image.open(io.BytesIO(file_bytes))
        return pytesseract.image_to_string(image, lang="rus+eng").strip()
    except pytesseract.TesseractNotFoundError:
        logger.warning("Бинарник tesseract не найден — OCR недоступен, чек уйдёт на ручную проверку")
        return ""
    except Exception as exc:
        logger.warning("Не удалось распознать текст на изображении чека: %s", exc)
        return ""
