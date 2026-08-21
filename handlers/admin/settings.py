from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
from config import ADMIN_IDS
from db.crud import get_setting, set_setting, get_categories, update_category_price
from keyboards.admin_kb import admin_back_kb
from states.states import AdminStates

router = Router()

def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@router.callback_query(F.data == "admin_settings")
async def show_settings(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    delivery = await get_setting("delivery_cost") or "300"
    requisites = await get_setting("payment_requisites") or "—"
    pickup = await get_setting("pickup_address") or "не указан"
    contact = await get_setting("manager_contact") or "не задан"
    card = await get_setting("payment_card") or "—"
    phone_sbp = await get_setting("payment_phone_sbp") or "—"
    wallet = await get_setting("payment_wallet") or "—"
    recipient = await get_setting("payment_recipient_name") or "—"
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    text = (
        f"⚙️ *Настройки*\n\nСтоимость доставки: {delivery} ₽\n"
        f"Карта: {card}\nСБП (телефон): {phone_sbp}\nКошелёк: {wallet}\nПолучатель: {recipient}\n"
        f"Реквизиты (текст, fallback): {requisites}\nАдрес самовывоза: {pickup}\nКонтакт менеджера: {contact}"
    )
    buttons = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить стоимость доставки", callback_data="edit_delivery_cost")],
        [InlineKeyboardButton(text="💳 Изменить карту", callback_data="edit_payment_card")],
        [InlineKeyboardButton(text="📱 Изменить телефон СБП", callback_data="edit_payment_phone_sbp")],
        [InlineKeyboardButton(text="👛 Изменить кошелёк", callback_data="edit_payment_wallet")],
        [InlineKeyboardButton(text="👤 Изменить имя получателя", callback_data="edit_payment_recipient_name")],
        [InlineKeyboardButton(text="✏️ Изменить реквизиты (текст)", callback_data="edit_requisites")],
        [InlineKeyboardButton(text="✏️ Изменить адрес самовывоза", callback_data="edit_pickup_address")],
        [InlineKeyboardButton(text="✏️ Изменить контакт менеджера", callback_data="edit_manager_contact")],
        [InlineKeyboardButton(text="← Назад", callback_data="admin_main")],
    ])
    await callback.message.edit_text(text, reply_markup=buttons, parse_mode="Markdown")
    await callback.answer()

# Структурированные реквизиты: callback → (ключ настройки, состояние, подсказка)
_PAYMENT_FIELDS = {
    "edit_payment_card": ("payment_card", AdminStates.waiting_new_payment_card, "Введите номер карты (16 цифр):"),
    "edit_payment_phone_sbp": ("payment_phone_sbp", AdminStates.waiting_new_payment_phone_sbp, "Введите телефон для СБП (например: +79001234567):"),
    "edit_payment_wallet": ("payment_wallet", AdminStates.waiting_new_payment_wallet, "Введите номер кошелька:"),
    "edit_payment_recipient_name": ("payment_recipient_name", AdminStates.waiting_new_payment_recipient_name, "Введите ФИО получателя платежа:"),
}

@router.callback_query(F.data.in_(_PAYMENT_FIELDS))
async def ask_payment_field(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    _, new_state, prompt = _PAYMENT_FIELDS[callback.data]
    await state.set_state(new_state)
    await callback.message.answer(prompt + "\n\nЧтобы очистить поле, отправьте «-».")
    await callback.answer()

@router.message(StateFilter(
    AdminStates.waiting_new_payment_card,
    AdminStates.waiting_new_payment_phone_sbp,
    AdminStates.waiting_new_payment_wallet,
    AdminStates.waiting_new_payment_recipient_name,
))
async def set_payment_field(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    current = await state.get_state()
    key = next(k for k, (_, st, _) in _PAYMENT_FIELDS.items() if st.state == current)
    value = message.text.strip()
    await set_setting(key, "" if value == "-" else value)
    await state.clear()
    await message.answer("✅ Реквизит обновлён." if value != "-" else "✅ Поле очищено.")

@router.callback_query(F.data == "edit_manager_contact")
async def ask_manager_contact(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_new_manager_contact)
    await callback.message.answer("Введите контакт менеджера (например: @username или телефон):")
    await callback.answer()

@router.message(StateFilter(AdminStates.waiting_new_manager_contact))
async def set_manager_contact(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await set_setting("manager_contact", message.text.strip())
    await state.clear()
    await message.answer("✅ Контакт менеджера обновлён.")

@router.callback_query(F.data == "edit_delivery_cost")
async def ask_delivery_cost(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_new_delivery_cost)
    await callback.message.answer("Введите новую стоимость доставки (₽):")
    await callback.answer()

@router.message(StateFilter(AdminStates.waiting_new_delivery_cost))
async def set_delivery_cost(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await set_setting("delivery_cost", message.text.strip())
    await state.clear()
    await message.answer(f"✅ Стоимость доставки обновлена: {message.text.strip()} ₽")

@router.callback_query(F.data == "edit_requisites")
async def ask_requisites(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_new_requisites)
    await callback.message.answer("Введите новые реквизиты для оплаты:")
    await callback.answer()

@router.message(StateFilter(AdminStates.waiting_new_requisites))
async def set_requisites(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await set_setting("payment_requisites", message.text.strip())
    await state.clear()
    await message.answer("✅ Реквизиты обновлены.")

@router.callback_query(F.data == "edit_pickup_address")
async def ask_pickup_address(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_new_pickup_address)
    await callback.message.answer("Введите адрес самовывоза:")
    await callback.answer()

@router.message(StateFilter(AdminStates.waiting_new_pickup_address))
async def set_pickup_address(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await set_setting("pickup_address", message.text.strip())
    await state.clear()
    await message.answer("✅ Адрес самовывоза обновлён.")

@router.callback_query(F.data == "admin_prices")
async def show_prices(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    categories = await get_categories(active_only=False)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = [[InlineKeyboardButton(text=f"{c.name} — {c.default_price:.0f} ₽", callback_data=f"edit_price_{c.slug}")] for c in categories]
    buttons.append([InlineKeyboardButton(text="← Назад", callback_data="admin_main")])
    await callback.message.edit_text("💰 Цены по категориям:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@router.callback_query(F.data.startswith("edit_price_"))
async def ask_new_category_price(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    slug = callback.data.replace("edit_price_", "")
    await state.update_data(slug=slug)
    await state.set_state(AdminStates.waiting_new_category_price)
    await callback.message.answer("Введите новую цену по умолчанию (₽):")
    await callback.answer()

@router.message(StateFilter(AdminStates.waiting_new_category_price))
async def set_new_category_price(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await update_category_price(data["slug"], float(message.text.strip()))
    await state.clear()
    await message.answer("✅ Цена категории обновлена.")
