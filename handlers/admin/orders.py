from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from config import ADMIN_IDS
from db.crud import get_orders_list, get_order_by_id, update_order_status, restore_stock_for_order
from db.models import OrderStatus
from keyboards.admin_kb import admin_main_menu_kb, admin_back_kb, admin_orders_kb, admin_order_card_kb
from services.logger import log

router = Router()

def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@router.message(F.text == "/admin")
async def admin_panel(message):
    if not _is_admin(message.from_user.id):
        return
    await message.answer("⚙️ *Панель администратора*", reply_markup=admin_main_menu_kb(), parse_mode="Markdown")

@router.callback_query(F.data == "admin_main")
async def admin_main(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    await callback.message.edit_text("⚙️ *Панель администратора*", reply_markup=admin_main_menu_kb(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "admin_orders")
async def show_orders(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    orders = await get_orders_list(limit=30)
    if not orders:
        await callback.message.edit_text("Заказов нет.", reply_markup=admin_back_kb())
        await callback.answer()
        return
    await callback.message.edit_text("📋 *Заказы* (нажмите для карточки):", reply_markup=admin_orders_kb(orders), parse_mode="Markdown")
    await callback.answer()

def _order_card_text(order) -> str:
    lines = [
        f"📋 *Заказ №{order.id}* — {order.status.value}",
        "",
        f"Клиент: {order.full_name or '—'}",
        f"Телефон: {order.phone or '—'}",
        f"Город: {order.city or '—'}",
        f"Пункт 5Post: {order.pickup_point or '—'}",
    ]
    if order.comment:
        lines.append(f"Комментарий: {order.comment}")
    lines.append("")
    for oi in order.items:
        lines.append(f"• {oi.catalog_item.category.name}, фото №{oi.catalog_item.photo_number} — {oi.quantity} шт. × {oi.price_at_order:.0f} ₽")
    lines += [
        "",
        f"Растения: {order.plants_cost:.0f} ₽ | Доставка: {order.delivery_cost:.0f} ₽",
        f"Итого: {order.total_cost:.0f} ₽ | Предоплата: {order.prepayment:.0f} ₽ | Остаток: {order.remainder:.0f} ₽",
    ]
    if order.track_number:
        lines.append(f"Трек: {order.track_number}")
    return "\n".join(lines)

@router.callback_query(F.data.startswith("admin_order_"))
async def show_order_card(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    order_id = int(callback.data.replace("admin_order_", ""))
    order = await get_order_by_id(order_id)
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    await callback.message.edit_text(_order_card_text(order), reply_markup=admin_order_card_kb(order_id), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("admin_complete_"))
async def complete_order(callback: CallbackQuery, bot: Bot) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    order_id = int(callback.data.replace("admin_complete_", ""))
    await update_order_status(order_id, OrderStatus.COMPLETED)
    await log("order_completed", order_id=order_id, user_id=callback.from_user.id)
    order = await get_order_by_id(order_id)
    try:
        await bot.send_message(order.user.telegram_id, f"✅ Ваш заказ №{order.id} завершён. Спасибо за покупку!")
    except Exception:
        pass
    await callback.message.edit_text(f"✅ Заказ №{order_id} завершён.", reply_markup=admin_back_kb())
    from services.export import send_export_to_admin
    await send_export_to_admin(bot, caption=f"📊 Выгрузка обновлена: заказ №{order_id} завершён")
    await callback.answer()

@router.callback_query(F.data.startswith("admin_cancel_"))
async def cancel_order(callback: CallbackQuery, bot: Bot) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    order_id = int(callback.data.replace("admin_cancel_", ""))
    order = await get_order_by_id(order_id)
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    # Возвращаем остатки, если заказ был зарезервирован (не черновик)
    if order.status != OrderStatus.DRAFT:
        await restore_stock_for_order(order_id)
    await update_order_status(order_id, OrderStatus.CANCELLED)
    await log("order_cancelled_by_admin", order_id=order_id, user_id=callback.from_user.id)
    try:
        await bot.send_message(order.user.telegram_id, f"🚫 Ваш заказ №{order.id} отменён. Если вопрос — напишите менеджеру.")
    except Exception:
        pass
    await callback.message.edit_text(f"🚫 Заказ №{order_id} отменён, остатки возвращены.", reply_markup=admin_back_kb())
    from services.export import send_export_to_admin
    await send_export_to_admin(bot, caption=f"📊 Выгрузка обновлена: заказ №{order_id} отменён")
    await callback.answer()

@router.callback_query(F.data == "admin_export")
async def export_excel(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    from datetime import datetime
    from aiogram.types import BufferedInputFile
    from services.export import build_export_xlsx
    await callback.answer("Собираю выгрузку…")
    data = await build_export_xlsx()
    filename = f"pitomnik_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    await callback.message.answer_document(BufferedInputFile(data, filename=filename), caption="📥 Выгрузка базы: заказы, клиенты, позиции каталога")

@router.callback_query(F.data == "admin_stats")
async def show_stats(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    orders = await get_orders_list(limit=1000)
    total_revenue = sum(o.total_cost for o in orders)
    text = f"📊 *Статистика*\n\nВсего заказов: {len(orders)}\nСуммарный оборот: {total_revenue:.0f} ₽"
    await callback.message.edit_text(text, reply_markup=admin_back_kb(), parse_mode="Markdown")
    await callback.answer()
