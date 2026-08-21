from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
from config import ADMIN_IDS
from db.crud import get_orders_list, get_order_by_id, save_track_number
from db.models import OrderStatus
from keyboards.admin_kb import shipped_kb, admin_back_kb
from states.states import AdminStates
from services.logger import log
from services.sheets import update_order_status_in_sheets

router = Router()

def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@router.callback_query(F.data == "admin_shipping")
async def show_shipping_orders(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    orders = await get_orders_list(status=OrderStatus.PAYMENT_CONFIRMED)
    if not orders:
        await callback.message.edit_text("Нет заказов, готовых к отправке.", reply_markup=admin_back_kb())
        await callback.answer()
        return
    for o in orders:
        await callback.message.answer(f"№{o.id} — {o.full_name}\nПункт 5Post: {o.pickup_point}", reply_markup=shipped_kb(o.id))
    await callback.answer()

@router.callback_query(F.data.startswith("mark_shipped_"))
async def mark_shipped(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    order_id = int(callback.data.replace("mark_shipped_", ""))
    await state.update_data(order_id=order_id)
    await state.set_state(AdminStates.waiting_track_number)
    await callback.message.answer("Введите трек-номер 5Post:")
    await callback.answer()

@router.message(StateFilter(AdminStates.waiting_track_number))
async def process_track_number(message: Message, state: FSMContext, bot: Bot) -> None:
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    order_id = data["order_id"]
    track = message.text.strip()
    await save_track_number(order_id, track)
    await update_order_status_in_sheets(order_id, OrderStatus.SHIPPED.value)
    await log("track_number_added", order_id=order_id, user_id=message.from_user.id, details=track)
    order = await get_order_by_id(order_id)
    await bot.send_message(order.user.telegram_id, f"📦 Ваш заказ №{order.id} отправлен.\n\nТрек-номер:\n{track}")
    await state.clear()
    await message.answer(f"Трек-номер сохранён для заказа №{order_id}.")
    from services.export import send_export_to_admin
    await send_export_to_admin(bot, caption=f"📊 Выгрузка обновлена: заказ №{order_id} отправлен")
