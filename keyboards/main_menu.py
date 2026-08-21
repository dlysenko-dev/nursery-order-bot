from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from config import WEBAPP_URL

def main_menu_kb(has_draft: bool = False, is_employee: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🌿 Каталог растений", callback_data="catalog")],
        [InlineKeyboardButton(text="🛒 Мой заказ", callback_data="cart")],
        [InlineKeyboardButton(text="ℹ️ Доставка и оплата", callback_data="info_menu")],
        [InlineKeyboardButton(text="📋 Как оформить заказ", callback_data="how_to_order")],
        [InlineKeyboardButton(text="❓ Частые вопросы", callback_data="faq")],
        [InlineKeyboardButton(text="📞 Связаться с менеджером", callback_data="contact_manager")],
    ]
    if is_employee:
        buttons.append([InlineKeyboardButton(text="👤 Мой кабинет", callback_data="my_cabinet")])
    if WEBAPP_URL:
        buttons.insert(0, [InlineKeyboardButton(text="🌱 Открыть магазин", web_app=WebAppInfo(url=WEBAPP_URL))])
    if has_draft:
        buttons.insert(1, [InlineKeyboardButton(text="⚠️ Продолжить незавершённый заказ", callback_data="resume_order")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def info_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚚 Доставка (5Post)", callback_data="info_delivery")],
        [InlineKeyboardButton(text="💳 Оплата и предоплата", callback_data="info_payment")],
        [InlineKeyboardButton(text="📦 Посадочный материал (ОКС/ЗКС)", callback_data="info_planting")],
        [InlineKeyboardButton(text="← Назад", callback_data="main_menu")],
    ])

def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="← Назад в меню", callback_data="main_menu")]])
