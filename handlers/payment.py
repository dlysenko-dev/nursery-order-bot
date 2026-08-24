from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
import html
from config import ADMIN_IDS, DEFAULT_PREPAYMENT_PERCENT
from db.crud import (
    get_active_order, save_receipt, get_order_by_id,
    get_payment_requisites, set_order_paid, update_order_status,
)
from db.models import OrderStatus
from keyboards.admin_kb import payment_check_kb
from states.states import PaymentStates
from services.logger import log
from services.receipt_check import process_receipt
from services.receipt_check.pipeline import STATUS_AUTO_APPROVED, STATUS_NEEDS_REVIEW, STATUS_REJECTED
from services.sheets import save_order_to_sheets, update_order_status_in_sheets

router = Router()

@router.callback_query(F.data == "upload_receipt")
async def ask_for_receipt(callback: CallbackQuery, state: FSMContext) -> None:
    order = await get_active_order(callback.from_user.id)
    if not order or order.status not in (OrderStatus.AWAITING_PREPAYMENT, OrderStatus.RECEIPT_RECEIVED):
        await callback.answer("Заказ, ожидающий оплату, не найден", show_alert=True)
        return
    await state.update_data(order_id=order.id, kind="prepayment")
    await state.set_state(PaymentStates.waiting_receipt)
    await callback.message.answer(
        f"📎 Отправьте фото или файл чека по заказу №{order.id}.\n\n"
        f"К оплате сейчас: {order.prepayment:.0f} ₽ (полная оплата заказа).\n\n"
        f"Если передумали — /cancel"
    )
    await callback.answer()

@router.callback_query(F.data == "upload_receipt_remainder")
async def ask_for_remainder_receipt(callback: CallbackQuery, state: FSMContext) -> None:
    """Приём чека на остаток: предоплата уже подтверждена, остаток — ещё нет."""
    order = await get_active_order(callback.from_user.id)
    if not order or not order.prepayment_paid_at or order.remainder_paid_at:
        await callback.answer("Заказ, ожидающий оплату остатка, не найден", show_alert=True)
        return
    await state.update_data(order_id=order.id, kind="remainder")
    await state.set_state(PaymentStates.waiting_receipt)
    await callback.message.answer(
        f"📎 Отправьте фото или файл чека по заказу №{order.id}.\n\n"
        f"К оплате сейчас: {order.remainder:.0f} ₽ (остаток).\n\n"
        f"Если передумали — /cancel"
    )
    await callback.answer()

@router.message(StateFilter(PaymentStates.waiting_receipt), F.photo | F.document)
async def receive_receipt(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    order_id = data["order_id"]
    kind = data.get("kind", "prepayment")
    order = await get_order_by_id(order_id)
    if not order:
        await state.clear()
        await message.answer("Заказ не найден. Обратитесь к менеджеру.")
        return
    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    filename = message.document.file_name if message.document else f"{file_id}.jpg"

    # Скачиваем чек и прогоняем автопроверку
    try:
        tg_file = await bot.get_file(file_id)
        buf = await bot.download_file(tg_file.file_path)
        file_bytes = buf.read()
    except Exception as exc:
        print(f"Не удалось скачать чек по заказу №{order_id}: {exc}")
        file_bytes = b""
    requisites = await get_payment_requisites()
    payment, verdict = await process_receipt(
        file_bytes, filename, order, kind, requisites, receipt_file_id=file_id,
    )
    await state.clear()

    if payment.check_status == STATUS_REJECTED:
        await log("receipt_rejected_duplicate", user_id=message.from_user.id, order_id=order_id, details="; ".join(verdict.reasons))
        await message.answer(
            "❌ Такой чек уже использовался для оплаты другого заказа.\n\n"
            "Если вы уверены, что это ошибка — напишите менеджеру."
        )
        await _notify_admins_text(
            bot,
            f"⚠️ <b>Чек отклонён автоматически (дубликат)</b>\n\nЗаказ №{order.id}\nКлиент: {html.escape(order.full_name or '')}\nПричина: {html.escape('; '.join(verdict.reasons))}",
        )
        return

    if payment.check_status == STATUS_AUTO_APPROVED:
        await _apply_auto_approval(message, bot, order, payment, kind)
        return

    # needs_review — ручная проверка админом (прежний поток + причины сомнений)
    if kind == "prepayment":
        await save_receipt(order_id, file_id)
    await log("receipt_received", user_id=message.from_user.id, order_id=order_id, details=f"auto_check: {'; '.join(verdict.reasons)}")
    await save_order_to_sheets(await get_order_by_id(order_id))
    await message.answer("✅ Чек получен.\n\nЗаявка отправлена на проверку оплаты.\n\nОжидайте подтверждения.")
    order = await get_order_by_id(order_id)
    amount = order.prepayment if kind == "prepayment" else order.remainder
    kind_label = "предоплата" if kind == "prepayment" else "остаток"
    reasons_text = "\n".join(f"• {html.escape(r)}" for r in verdict.reasons) or "• —"
    admin_text = (
        f"🔔 <b>Новая заявка на проверку оплаты</b>\n\n"
        f"Заказ №{order.id} ({kind_label})\n\n"
        f"Клиент: {html.escape(order.full_name or '')}\nТелефон: {html.escape(order.phone or '')}\n"
        f"Город: {html.escape(order.city or '')}\nПункт 5Post: {html.escape(order.pickup_point or '')}\n\n"
        f"Итого: {order.total_cost:.0f} ₽\nК оплате ({kind_label}): {amount:.0f} ₽\n\n"
        f"🤖 Автопроверка — нужна ручная проверка:\n{reasons_text}\n\n"
        f"Статус: Чек получен\n📎 Чек прикреплён"
    )
    from db.crud import get_responsible_notify_ids
    for admin_id in await get_responsible_notify_ids(order.user_id, order_employee_id=order.employee_id):
        try:
            if message.photo:
                await bot.send_photo(admin_id, file_id, caption=admin_text, reply_markup=payment_check_kb(order.id), parse_mode="HTML")
            else:
                await bot.send_document(admin_id, file_id, caption=admin_text, reply_markup=payment_check_kb(order.id), parse_mode="HTML")
        except Exception as exc:
            print(f"Не удалось отправить уведомление админу {admin_id}: {exc}")

async def _apply_auto_approval(message: Message, bot: Bot, order, payment, kind: str) -> None:
    """Автоподтверждение: отмечаем оплату, уведомляем клиента и админов, обновляем Sheets/xlsx."""
    await set_order_paid(order.id, kind, payment.paid_at)
    await log("payment_auto_approved", user_id=message.from_user.id, order_id=order.id, details=f"kind={kind} amount={payment.amount}")
    if kind == "prepayment":
        await update_order_status(order.id, OrderStatus.PAYMENT_CONFIRMED)
        await update_order_status_in_sheets(order.id, OrderStatus.PAYMENT_CONFIRMED.value)
        await message.answer(
            f"✅ Оплата подтверждена автоматически!\n\nВаш заказ №{order.id} принят.\n\n"
            f"После отправки через 5Post мы сообщим вам трек-номер."
        )
        admin_text = (
            f"🤖 <b>Оплата подтверждена автоматически</b>\n\nЗаказ №{order.id}\n"
            f"Клиент: {html.escape(order.full_name or '')}\nСумма: {payment.amount:.0f} ₽ (предоплата)\n"
            f"Операция: {html.escape(payment.operation_id or '—')}\n\nСтатус: оплата подтверждена"
        )
    else:
        await message.answer(
            f"✅ Остаток по заказу №{order.id} подтверждён автоматически.\n\nЗаказ полностью оплачен, спасибо!"
        )
        admin_text = (
            f"🤖 <b>Остаток подтверждён автоматически</b>\n\nЗаказ №{order.id}\n"
            f"Клиент: {html.escape(order.full_name or '')}\nСумма: {payment.amount:.0f} ₽ (остаток)\n"
            f"Операция: {html.escape(payment.operation_id or '—')}\n\nЗаказ полностью оплачен"
        )
    await _notify_admins_text(bot, admin_text, order.user_id, order_employee_id=order.employee_id)
    from services.export import send_export_to_admin
    await send_export_to_admin(bot, caption=f"📊 Выгрузка обновлена: оплата подтверждена автоматически по заказу №{order.id}")

async def _notify_admins_text(bot: Bot, text: str, user_id: int | None = None, order_employee_id: int | None = None) -> None:
    from db.crud import get_responsible_notify_ids
    for admin_id in await get_responsible_notify_ids(user_id, order_employee_id=order_employee_id):
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception as exc:
            print(f"Не удалось отправить уведомление админу {admin_id}: {exc}")

@router.message(StateFilter(PaymentStates.waiting_receipt))
async def wrong_receipt_format(message: Message) -> None:
    await message.answer("Пожалуйста, отправьте фотографию или файл (документ) с чеком.")
