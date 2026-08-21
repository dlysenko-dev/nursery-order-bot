from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def admin_main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Заказы", callback_data="admin_orders")],
        [InlineKeyboardButton(text="💳 Проверка оплат", callback_data="admin_payments")],
        [InlineKeyboardButton(text="📦 Заказы на отправку", callback_data="admin_shipping")],
        [InlineKeyboardButton(text="🌱 Товары", callback_data="admin_items")],
        [InlineKeyboardButton(text="💰 Цены", callback_data="admin_prices")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📥 Выгрузка Excel", callback_data="admin_export")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings")],
    ])

def payment_check_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оплата подтверждена", callback_data=f"confirm_payment_{order_id}")],
        [InlineKeyboardButton(text="❌ Оплата не подтверждена", callback_data=f"reject_payment_{order_id}")],
        [InlineKeyboardButton(text="💬 Написать клиенту", callback_data=f"msg_client_{order_id}")],
    ])

def shipped_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📦 Заказ отправлен", callback_data=f"mark_shipped_{order_id}")]])

def admin_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="← Назад в админ-меню", callback_data="admin_main")]])

def admin_orders_kb(orders) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(
        text=f"№{o.id} — {o.status.value} — {o.full_name or '—'} — {o.total_cost:.0f} ₽",
        callback_data=f"admin_order_{o.id}",
    )] for o in orders]
    buttons.append([InlineKeyboardButton(text="← Назад", callback_data="admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_order_card_kb(order_id: int, show_remainder: bool = False) -> InlineKeyboardMarkup:
    buttons = []
    if show_remainder:
        buttons.append([InlineKeyboardButton(text="💰 Запросить остаток", callback_data=f"admin_request_remainder_{order_id}")])
    buttons += [
        [InlineKeyboardButton(text="✅ Завершить заказ", callback_data=f"admin_complete_{order_id}")],
        [InlineKeyboardButton(text="🚫 Отменить заказ", callback_data=f"admin_cancel_{order_id}")],
        [InlineKeyboardButton(text="← К списку заказов", callback_data="admin_orders")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
