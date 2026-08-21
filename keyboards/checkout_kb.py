from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def phone_request_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Отправить мой номер", request_contact=True)], [KeyboardButton(text="✍️ Ввести вручную")]], resize_keyboard=True, one_time_keyboard=True)

def skip_comment_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data="skip_comment")],
        [InlineKeyboardButton(text="← Назад", callback_data="checkout_back")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_checkout")],
    ])

def checkout_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data="checkout_back")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_checkout")],
    ])

def checkout_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_checkout")],
    ])

def data_mode_kb(saved_summary: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Как в прошлый раз", callback_data="checkout_repeat")],
        [InlineKeyboardButton(text="✏️ Ввести заново", callback_data="checkout_fresh")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_checkout")],
    ])

def order_preview_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Всё верно", callback_data="confirm_order")],
        [InlineKeyboardButton(text="✏️ Изменить данные", callback_data="edit_customer_data")],
        [InlineKeyboardButton(text="🛒 Изменить заказ", callback_data="edit_cart")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_checkout")],
    ])

def template_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 Шаблон заявки", callback_data="order_template")]])

def prepayment_kb(pay_url: str | None = None) -> InlineKeyboardMarkup:
    buttons = []
    if pay_url:
        buttons.append([InlineKeyboardButton(text="🌐 Страница оплаты", url=pay_url)])
    buttons += [
        [InlineKeyboardButton(text="📎 Отправить чек", callback_data="upload_receipt")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def remainder_payment_kb(pay_url: str | None = None) -> InlineKeyboardMarkup:
    buttons = []
    if pay_url:
        buttons.append([InlineKeyboardButton(text="🌐 Страница оплаты", url=pay_url)])
    buttons += [
        [InlineKeyboardButton(text="📎 Отправить чек", callback_data="upload_receipt_remainder")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def receipt_retry_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📎 Отправить чек повторно", callback_data="upload_receipt")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu")],
    ])
