"""Публичная страница оплаты /pay/{token}: информация о заказе и загрузка чека.

Токен в URL — единственная авторизация (ссылка приходит клиенту лично).
Пайплайн проверки чека общий с ботом: services/receipt_check.process_receipt.
"""
from __future__ import annotations

import html
import json
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from config import ADMIN_IDS, BOT_TOKEN, DEFAULT_PREPAYMENT_PERCENT
from db import crud
from db.models import OrderStatus
from services.receipt_check import process_receipt
from services.receipt_check.pipeline import (
    STATUS_AUTO_APPROVED,
    STATUS_NEEDS_REVIEW,
    STATUS_REJECTED,
)

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_RECEIPT_SIZE = 10 * 1024 * 1024  # 10 МБ


def _due_stage(order) -> tuple[str | None, float]:
    """Какой платёж сейчас ждём: предоплата, остаток или ничего (всё оплачено)."""
    if not order.prepayment_paid_at:
        return "prepayment", order.prepayment
    if order.remainder > 0 and not order.remainder_paid_at:
        return "remainder", order.remainder
    return None, 0.0


def _order_public_view(order, requisites_text: str, manager_contact: str) -> dict:
    due_kind, due_amount = _due_stage(order)
    return {
        "order_id": order.id,
        "status": order.status.value,
        "full_name": order.full_name,
        "total_cost": order.total_cost,
        "delivery_cost": order.delivery_cost,
        "prepayment": order.prepayment,
        "remainder": order.remainder,
        "prepayment_percent": DEFAULT_PREPAYMENT_PERCENT,
        "prepayment_paid": bool(order.prepayment_paid_at),
        "remainder_paid": bool(order.remainder_paid_at),
        "due_kind": due_kind,
        "due_amount": due_amount,
        "requisites": requisites_text,
        "manager_contact": manager_contact,
        "site_token": order.user.site_token if order.user else None,  # для чата на странице оплаты
        "cancelled": order.status == OrderStatus.CANCELLED,
    }


@router.get("/pay/{pay_token}")
async def pay_info(pay_token: str) -> dict:
    """Сводка по заказу для страницы оплаты: суммы, стадия, реквизиты."""
    order = await crud.get_order_by_pay_token(pay_token)
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    requisites = crud.format_requisites_text(await crud.get_payment_requisites())
    manager_contact = (await crud.get_setting("manager_contact")) or ""
    return _order_public_view(order, requisites, manager_contact)


@router.post("/pay/{pay_token}/receipt")
async def pay_upload_receipt(pay_token: str, file: UploadFile = File(...)) -> dict:
    """Приём чека со страницы оплаты: автопроверка → подтверждение / админу / отказ."""
    order = await crud.get_order_by_pay_token(pay_token)
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    if order.status == OrderStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Заказ отменён")

    due_kind, due_amount = _due_stage(order)
    if not due_kind:
        raise HTTPException(status_code=400, detail="Заказ уже полностью оплачен")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Пустой файл")
    if len(file_bytes) > MAX_RECEIPT_SIZE:
        raise HTTPException(status_code=400, detail="Файл слишком большой (максимум 10 МБ)")

    filename = file.filename or "receipt"
    requisites = await crud.get_payment_requisites()
    payment, verdict = await process_receipt(
        file_bytes, filename, order, due_kind, requisites, receipt_file_id=None,
    )
    await crud.log_event(
        "receipt_uploaded_web",
        user_telegram_id=order.user.telegram_id if order.user else None,
        order_id=order.id,
        details=f"kind={due_kind} status={payment.check_status}",
    )

    if payment.check_status == STATUS_REJECTED:
        await _notify_admins(
            f"⚠️ <b>Чек с сайта отклонён (дубликат)</b>\n\nЗаказ №{order.id}\n"
            f"Клиент: {html.escape(order.full_name or '')}\n"
            f"Причина: {html.escape('; '.join(verdict.reasons))}",
        )
        return {
            "result": STATUS_REJECTED,
            "message": "Такой чек уже использовался для оплаты другого заказа. "
                       "Если вы уверены, что это ошибка — свяжитесь с менеджером.",
            "reasons": verdict.reasons,
        }

    if payment.check_status == STATUS_AUTO_APPROVED:
        await _apply_auto_approval(order, payment, due_kind)
        return {
            "result": STATUS_AUTO_APPROVED,
            "message": f"Оплата ({'предоплата' if due_kind == 'prepayment' else 'остаток'}) "
                       f"подтверждена автоматически. Спасибо!",
        }

    # needs_review — чек и причины сомнений уходят админам
    kind_label = "предоплата" if due_kind == "prepayment" else "остаток"
    reasons_text = "\n".join(f"• {html.escape(r)}" for r in verdict.reasons) or "• —"
    admin_text = (
        f"🔔 <b>Чек с сайта — нужна ручная проверка</b>\n\n"
        f"Заказ №{order.id} ({kind_label})\n"
        f"Клиент: {html.escape(order.full_name or '')}\nТелефон: {html.escape(order.phone or '')}\n"
        f"К оплате ({kind_label}): {due_amount:.0f} ₽\n\n"
        f"🤖 Автопроверка:\n{reasons_text}"
    )
    await _notify_admins(admin_text, file_bytes=file_bytes, filename=filename, order_id=order.id)
    try:
        from services.sheets import save_order_to_sheets

        await save_order_to_sheets(await crud.get_order_by_id(order.id))
    except Exception as exc:
        logger.warning("Не удалось обновить Google Sheets по заказу №%s: %s", order.id, exc)
    return {
        "result": STATUS_NEEDS_REVIEW,
        "message": "Чек получен и отправлен на проверку менеджеру. "
                   "Мы подтвердим оплату в ближайшее время.",
        "reasons": verdict.reasons,
    }


async def _apply_auto_approval(order, payment, kind: str) -> None:
    """Автоподтверждение с сайта: отметить оплату, обновить статус, уведомить клиента и админов."""
    await crud.set_order_paid(order.id, kind, payment.paid_at)
    if kind == "prepayment":
        await crud.update_order_status(order.id, OrderStatus.PAYMENT_CONFIRMED)
        try:
            from services.sheets import update_order_status_in_sheets

            await update_order_status_in_sheets(order.id, OrderStatus.PAYMENT_CONFIRMED.value)
        except Exception as exc:
            logger.warning("Не удалось обновить статус в Sheets по заказу №%s: %s", order.id, exc)
        admin_text = (
            f"🤖 <b>Оплата подтверждена автоматически (сайт)</b>\n\nЗаказ №{order.id}\n"
            f"Клиент: {html.escape(order.full_name or '')}\nСумма: {payment.amount:.0f} ₽ (предоплата)\n"
            f"Операция: {html.escape(payment.operation_id or '—')}"
        )
        client_text = (
            f"✅ Оплата подтверждена автоматически!\n\nВаш заказ №{order.id} принят.\n\n"
            f"После отправки через 5Post мы сообщим вам трек-номер."
        )
    else:
        admin_text = (
            f"🤖 <b>Остаток подтверждён автоматически (сайт)</b>\n\nЗаказ №{order.id}\n"
            f"Клиент: {html.escape(order.full_name or '')}\nСумма: {payment.amount:.0f} ₽ (остаток)\n"
            f"Операция: {html.escape(payment.operation_id or '—')}\n\nЗаказ полностью оплачен"
        )
        client_text = f"✅ Остаток по заказу №{order.id} подтверждён автоматически.\n\nЗаказ полностью оплачен, спасибо!"
    await _notify_admins(admin_text)
    if order.user and order.user.telegram_id:
        await _send_to_user(order.user.telegram_id, client_text)
    await _send_export(f"📊 Выгрузка обновлена: оплата подтверждена автоматически по заказу №{order.id}")


async def _notify_admins(
    text: str,
    file_bytes: bytes | None = None,
    filename: str = "receipt",
    order_id: int | None = None,
) -> None:
    """Сообщение админам; при наличии файла — с чеком и кнопками ручной проверки."""
    if not BOT_TOKEN or not ADMIN_IDS:
        return
    try:
        from aiogram import Bot
        from aiogram.types import BufferedInputFile

        bot = Bot(token=BOT_TOKEN)
        try:
            reply_markup = None
            if order_id is not None:
                from keyboards.admin_kb import payment_check_kb

                reply_markup = payment_check_kb(order_id)
            for admin_id in ADMIN_IDS:
                try:
                    if file_bytes:
                        await bot.send_document(
                            admin_id,
                            BufferedInputFile(file_bytes, filename=filename),
                            caption=text,
                            reply_markup=reply_markup,
                            parse_mode="HTML",
                        )
                    else:
                        await bot.send_message(admin_id, text, parse_mode="HTML")
                except Exception as exc:
                    logger.warning("Не удалось уведомить админа %s: %s", admin_id, exc)
        finally:
            await bot.session.close()
    except Exception as exc:
        logger.warning("Не удалось уведомить админов: %s", exc)


async def _send_to_user(telegram_id: int, text: str) -> None:
    if not BOT_TOKEN:
        return
    try:
        from aiogram import Bot

        bot = Bot(token=BOT_TOKEN)
        try:
            await bot.send_message(telegram_id, text)
        finally:
            await bot.session.close()
    except Exception as exc:
        logger.warning("Не удалось написать клиенту %s: %s", telegram_id, exc)


async def _send_export(caption: str) -> None:
    if not BOT_TOKEN or not ADMIN_IDS:
        return
    try:
        from aiogram import Bot

        from services.export import send_export_to_admin

        bot = Bot(token=BOT_TOKEN)
        try:
            await send_export_to_admin(bot, caption=caption)
        finally:
            await bot.session.close()
    except Exception as exc:
        logger.warning("Не удалось отправить выгрузку: %s", exc)
