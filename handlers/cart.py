from aiogram import Router, F
from aiogram.types import CallbackQuery
from config import DEFAULT_PREPAYMENT_PERCENT
from db.crud import get_draft_order, get_active_order, get_user_orders, remove_item_from_cart, clear_cart
from db.models import OrderStatus
from keyboards.cart_kb import cart_kb, empty_cart_kb, cart_item_remove_kb, active_order_kb, clear_cart_confirm_kb
from services.logger import log

router = Router()


def _cart_text(order) -> str:
    lines = ["🛒 *Ваш заказ*\n"]
    for oi in order.items:
        line_total = oi.quantity * oi.price_at_order
        lines.append(
            f"• {oi.catalog_item.category.name}, фото №{oi.catalog_item.photo_number}"
            f" — {oi.quantity} шт. × {oi.price_at_order:.0f} ₽ = {line_total:.0f} ₽"
        )
    lines += [
        "",
        f"Стоимость растений: {order.plants_cost:.0f} ₽",
        f"Доставка: {order.delivery_cost:.0f} ₽",
        f"Итого: *{order.total_cost:.0f} ₽*",
        f"Предоплата {DEFAULT_PREPAYMENT_PERCENT}%: {order.prepayment:.0f} ₽",
        f"Остаток при получении: {order.remainder:.0f} ₽",
    ]
    return "\n".join(lines)


def _active_order_text(order) -> str:
    lines = [
        f"📦 *Заказ №{order.id}*",
        f"Статус: *{order.status.value}*",
        "",
        "Состав:",
    ]
    for oi in order.items:
        lines.append(f"• {oi.catalog_item.category.name}, фото №{oi.catalog_item.photo_number} — {oi.quantity} шт.")
    lines += [
        "",
        f"Итого: *{order.total_cost:.0f} ₽*",
        f"Предоплата {DEFAULT_PREPAYMENT_PERCENT}%: {order.prepayment:.0f} ₽",
        f"Остаток при получении: {order.remainder:.0f} ₽",
    ]
    if order.track_number:
        lines.append(f"\n🚚 Трек-номер: {order.track_number}")
    if order.status == OrderStatus.AWAITING_PREPAYMENT:
        lines.append("\nПосле оплаты отправьте чек кнопкой ниже.")
    return "\n".join(lines)


@router.callback_query(F.data == "cart")
async def show_cart(callback: CallbackQuery) -> None:
    from aiogram.exceptions import TelegramBadRequest
    order = await get_draft_order(callback.from_user.id)
    if order and order.items:
        text, kb = _cart_text(order), cart_kb()
        active = None
    else:
        active = await get_active_order(callback.from_user.id)
        if active:
            show_receipt = active.status in (OrderStatus.AWAITING_PREPAYMENT, OrderStatus.RECEIPT_RECEIVED)
            text, kb = _active_order_text(active), active_order_kb(show_receipt)
        else:
            text, kb = "🛒 Ваша корзина пуста.\n\nВыберите растения в каталоге.", empty_cart_kb()
    history = await get_user_orders(callback.from_user.id, limit=10)
    past = [o for o in history if o.status != OrderStatus.DRAFT and (not active or o.id != active.id)][:3]
    if past:
        text += "\n\n📜 *История заказов:*\n" + "\n".join(f"№{o.id} — {o.status.value} — {o.total_cost:.0f} ₽" for o in past)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except TelegramBadRequest:
        # Текущее сообщение — фото/медиа, текст отредактировать нельзя
        await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
        try:
            await callback.message.delete()
        except Exception:
            pass
    await callback.answer()


@router.callback_query(F.data == "edit_cart")
async def edit_cart(callback: CallbackQuery) -> None:
    order = await get_draft_order(callback.from_user.id)
    if not order or not order.items:
        await callback.answer("Корзина пуста", show_alert=True)
        return
    await callback.message.edit_text(
        "✏️ Нажмите на позицию, чтобы удалить её из заказа:",
        reply_markup=cart_item_remove_kb(order.items),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("remove_item_"))
async def remove_item(callback: CallbackQuery) -> None:
    order_item_id = int(callback.data.replace("remove_item_", ""))
    await remove_item_from_cart(order_item_id)
    await log("cart_item_removed", user_id=callback.from_user.id, details=f"order_item #{order_item_id}")
    await callback.answer("Позиция удалена")
    await show_cart(callback)


@router.callback_query(F.data == "clear_cart")
async def clear_cart_handler(callback: CallbackQuery) -> None:
    order = await get_draft_order(callback.from_user.id)
    if not order or not order.items:
        await callback.answer("Корзина пуста", show_alert=True)
        return
    await callback.message.edit_text(
        "🗑 Удалить все позиции из корзины?",
        reply_markup=clear_cart_confirm_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "clear_cart_yes")
async def clear_cart_confirm(callback: CallbackQuery) -> None:
    order = await get_draft_order(callback.from_user.id)
    if not order:
        await callback.answer("Корзина пуста", show_alert=True)
        return
    await clear_cart(order.id)
    await log("cart_cleared", user_id=callback.from_user.id, order_id=order.id)
    await callback.answer("🗑 Корзина очищена")
    await show_cart(callback)
