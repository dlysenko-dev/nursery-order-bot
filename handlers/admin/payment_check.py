from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
from config import ADMIN_IDS
from db.crud import get_order_by_id, update_order_status, set_admin_comment
from db.models import OrderStatus
from keyboards.admin_kb import admin_back_kb
from states.states import AdminStates
from services.logger import log
from services.sheets import update_order_status_in_sheets

router = Router()

def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@router.callback_query(F.data.startswith("confirm_payment_"))
async def confirm_payment(callback: CallbackQuery, bot: Bot) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    order_id = int(callback.data.replace("confirm_payment_", ""))
    await update_order_status(order_id, OrderStatus.PAYMENT_CONFIRMED)
    await update_order_status_in_sheets(order_id, OrderStatus.PAYMENT_CONFIRMED.value)
    await log("payment_confirmed", order_id=order_id, user_id=callback.from_user.id)
    order = await get_order_by_id(order_id)
    await bot.send_message(order.user.telegram_id, f"✅ Оплата подтверждена!\n\nВаш заказ №{order.id} принят.\n\nПосле отправки через 5Post мы сообщим вам трек-номер.")
    await callback.message.edit_text(f"✅ Оплата по заказу №{order_id} подтверждена.")
    from services.export import send_export_to_admin
    await send_export_to_admin(bot, caption=f"📊 Выгрузка обновлена: оплата подтверждена по заказу №{order_id}")
    await callback.answer()

@router.callback_query(F.data.startswith("reject_payment_"))
async def reject_payment(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    order_id = int(callback.data.replace("reject_payment_", ""))
    await state.update_data(order_id=order_id)
    await state.set_state(AdminStates.waiting_rejection_comment)
    await callback.message.answer("Комментарий администратора (например: «Необходимо повторно отправить чек。」):")
    await callback.answer()

@router.message(StateFilter(AdminStates.waiting_rejection_comment))
async def process_rejection_comment(message: Message, state: FSMContext, bot: Bot) -> None:
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    order_id = data["order_id"]
    comment = message.text.strip()
    await set_admin_comment(order_id, comment)
    # Возвращаем заказ в ожидание предоплаты — клиент сможет отправить чек повторно
    await update_order_status(order_id, OrderStatus.AWAITING_PREPAYMENT)
    await log("payment_rejected", order_id=order_id, user_id=message.from_user.id, details=comment)
    order = await get_order_by_id(order_id)
    from keyboards.checkout_kb import receipt_retry_kb
    await bot.send_message(
        order.user.telegram_id,
        f"❌ Оплата по заказу №{order.id} не подтверждена.\n\nКомментарий: {comment}\n\nПожалуйста, отправьте корректный чек ещё раз.",
        reply_markup=receipt_retry_kb(),
    )
    await state.clear()
    await message.answer(f"Комментарий отправлен клиенту по заказу №{order_id}.")
    from services.export import send_export_to_admin
    await send_export_to_admin(bot, caption=f"📊 Выгрузка обновлена: оплата отклонена по заказу №{order_id}")

@router.callback_query(F.data.startswith("msg_client_"))
async def msg_client_prompt(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    order_id = callback.data.replace("msg_client_", "")
    order = await get_order_by_id(int(order_id))
    await callback.message.answer(f"Напишите клиенту напрямую: {order.phone} (username: @{order.user.username or 'нет'})")
    await callback.answer()

@router.callback_query(F.data == "admin_payments")
async def show_pending_payments(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    from db.crud import get_orders_list
    orders = await get_orders_list(status=OrderStatus.ON_REVIEW)
    if not orders:
        await callback.message.edit_text("Нет заказов на проверке оплаты.", reply_markup=admin_back_kb())
        await callback.answer()
        return
    lines = [f"№{o.id} — {o.full_name} — {o.total_cost:.0f} ₽" for o in orders]
    await callback.message.edit_text("💳 *На проверке:*\n\n" + "\n".join(lines), reply_markup=admin_back_kb(), parse_mode="Markdown")
    await callback.answer()
