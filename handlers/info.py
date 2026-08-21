from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from db.crud import get_setting
from data.faq import FAQ_ITEMS
from keyboards.main_menu import back_to_menu_kb, info_menu_kb

router = Router()

@router.callback_query(F.data == "info_menu")
async def show_info_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text("ℹ️ *Информация*\n\nВыберите раздел:", reply_markup=info_menu_kb(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "info_delivery")
async def show_delivery_info(callback: CallbackQuery) -> None:
    text = "🚚 Отправляем заказы через 5Post.\n\nСредняя стоимость доставки — около 300 ₽.\n\nСтоимость доставки добавляется к заказу.\n\nПри оформлении бот автоматически рассчитает итоговую сумму и предоплату 30%."
    await callback.message.edit_text(text, reply_markup=back_to_menu_kb())
    await callback.answer()

@router.callback_query(F.data == "info_payment")
async def show_payment_info(callback: CallbackQuery) -> None:
    text = "💳 Для бронирования заказа необходимо внести предоплату 30% от общей суммы заказа вместе с доставкой.\n\nПосле формирования заказа бот покажет точную сумму предоплаты и реквизиты.\n\nПосле оплаты необходимо отправить чек в бот."
    await callback.message.edit_text(text, reply_markup=back_to_menu_kb())
    await callback.answer()

@router.callback_query(F.data == "info_planting")
async def show_planting_info(callback: CallbackQuery) -> None:
    text = "Возможен посадочный материал:\n\n🌱 Открытая корневая система (ОКС)\nУпаковка — стрейч-плёнка.\n\n🌱 Закрытая корневая система (ЗКС)\nОтправка — в горшке.\n\nЕсли доступен выбор, покупатель может указать желаемый вариант."
    await callback.message.edit_text(text, reply_markup=back_to_menu_kb())
    await callback.answer()

@router.callback_query(F.data == "faq")
async def show_faq_list(callback: CallbackQuery) -> None:
    buttons = [[InlineKeyboardButton(text=item["question"], callback_data=f"faq_{item['id']}")] for item in FAQ_ITEMS]
    buttons.append([InlineKeyboardButton(text="← Назад", callback_data="main_menu")])
    await callback.message.edit_text("❓ *Частые вопросы*\n\nВыберите вопрос:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("faq_"))
async def show_faq_answer(callback: CallbackQuery) -> None:
    faq_id = callback.data.replace("faq_", "")
    item = next((f for f in FAQ_ITEMS if f["id"] == faq_id), None)
    if not item:
        await callback.answer("Вопрос не найден", show_alert=True)
        return
    text = f"{item['question']}\n\n{item['answer']}"
    if faq_id == "pickup":
        pickup_address = await get_setting("pickup_address")
        if pickup_address:
            text += f"\n\nАдрес самовывоза: {pickup_address}"
    buttons = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="← Назад к вопросам", callback_data="faq")]])
    await callback.message.edit_text(text, reply_markup=buttons, parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "how_to_order")
async def show_how_to_order(callback: CallbackQuery) -> None:
    item = next(f for f in FAQ_ITEMS if f["id"] == "how_to_order")
    text = f"{item['question']}\n\n{item['answer']}"
    cover_file_id = await get_setting("how_to_order_file_id")
    if cover_file_id:
        await callback.message.answer_photo(photo=cover_file_id, caption=text, reply_markup=back_to_menu_kb(), parse_mode="Markdown")
        await callback.message.delete()
    else:
        await callback.message.edit_text(text, reply_markup=back_to_menu_kb(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "contact_manager")
async def contact_manager(callback: CallbackQuery) -> None:
    contact = await get_setting("manager_contact") or "@DanilLysenko"
    text = (
        f"📞 *Связь с менеджером*\n\n{contact}\n\n"
        "Напишите нам — ответим в ближайшее время.\n"
        "Вы также можете оформить заказ самостоятельно через каталог."
    )
    await callback.message.edit_text(text, reply_markup=back_to_menu_kb(), parse_mode="Markdown")
    await callback.answer()
