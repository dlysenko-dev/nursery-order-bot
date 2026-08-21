from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def cart_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout_start")],
        [InlineKeyboardButton(text="➕ Продолжить покупки", callback_data="catalog")],
        [InlineKeyboardButton(text="✏️ Изменить заказ", callback_data="edit_cart")],
        [InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear_cart")],
        [InlineKeyboardButton(text="← Назад", callback_data="main_menu")],
    ])

def empty_cart_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌿 Перейти в каталог", callback_data="catalog")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")],
    ])

def active_order_kb(show_receipt_button: bool) -> InlineKeyboardMarkup:
    buttons = []
    if show_receipt_button:
        buttons.append([InlineKeyboardButton(text="📎 Отправить чек", callback_data="upload_receipt")])
    buttons.append([InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def clear_cart_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, очистить", callback_data="clear_cart_yes")],
        [InlineKeyboardButton(text="← Отмена", callback_data="cart")],
    ])

def cart_item_remove_kb(order_items) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=f"🗑 Удалить: {oi.catalog_item.category.name} №{oi.catalog_item.photo_number}", callback_data=f"remove_item_{oi.id}")] for oi in order_items]
    buttons.append([InlineKeyboardButton(text="← Назад к заказу", callback_data="cart")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
