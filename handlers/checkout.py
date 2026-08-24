from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
import html
from config import DEFAULT_PREPAYMENT_PERCENT
from db.crud import get_draft_order, save_customer_data, update_order_status, get_order_by_id, get_user_by_telegram_id, save_user_contact_data
from db.models import OrderStatus
from keyboards.checkout_kb import phone_request_kb, skip_comment_kb, order_preview_kb, template_kb, checkout_back_kb, checkout_cancel_kb, data_mode_kb
from states.states import CheckoutStates
from services.logger import log

router = Router()

@router.callback_query(F.data == "checkout_start")
async def checkout_start(callback: CallbackQuery, state: FSMContext) -> None:
    order = await get_draft_order(callback.from_user.id)
    if not order or not order.items:
        await callback.answer("Корзина пуста — нельзя оформить пустой заказ.", show_alert=True)
        return
    await state.update_data(order_id=order.id)
    user = await get_user_by_telegram_id(callback.from_user.id)
    if user and user.full_name and user.phone and user.city and user.pickup_point:
        await state.set_state(CheckoutStates.choosing_data_mode)
        summary = f"ФИО: {user.full_name}\nТелефон: {user.phone}\nГород: {user.city}\nПункт 5Post: {user.pickup_point}"
        await callback.message.answer(f"📋 Использовать данные прошлого заказа?\n\n{summary}", reply_markup=data_mode_kb(summary))
    else:
        await state.set_state(CheckoutStates.collecting_name)
        await callback.message.answer("Как вас зовут?\n\nУкажите имя или ФИО.", reply_markup=checkout_cancel_kb())
    await callback.answer()

@router.callback_query(F.data == "checkout_repeat", StateFilter(CheckoutStates.choosing_data_mode))
async def checkout_repeat(callback: CallbackQuery, state: FSMContext) -> None:
    user = await get_user_by_telegram_id(callback.from_user.id)
    if not user:
        await callback.answer("Данные не найдены", show_alert=True)
        return
    await state.update_data(full_name=user.full_name, phone=user.phone, city=user.city, pickup_point=user.pickup_point)
    await state.set_state(CheckoutStates.collecting_comment)
    await callback.message.answer("✅ Данные подставлены.\n\n💬 Если хотите, оставьте комментарий к заказу.", reply_markup=skip_comment_kb())
    await callback.answer()

@router.callback_query(F.data == "checkout_fresh", StateFilter(CheckoutStates.choosing_data_mode))
async def checkout_fresh(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CheckoutStates.collecting_name)
    await callback.message.answer("Как вас зовут?\n\nУкажите имя или ФИО.", reply_markup=checkout_cancel_kb())
    await callback.answer()

@router.message(StateFilter(CheckoutStates.collecting_name))
async def collect_name(message: Message, state: FSMContext) -> None:
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, укажите имя.")
        return
    await state.update_data(full_name=message.text.strip())
    await state.set_state(CheckoutStates.collecting_phone)
    await message.answer("📱 Укажите номер телефона для связи.\n\nЧтобы прервать оформление, отправьте /cancel", reply_markup=phone_request_kb())

@router.message(StateFilter(CheckoutStates.collecting_phone), F.contact)
async def collect_phone_contact(message: Message, state: FSMContext) -> None:
    await state.update_data(phone=message.contact.phone_number)
    await state.set_state(CheckoutStates.collecting_city)
    await message.answer("📍 Укажите город получения.", reply_markup=checkout_back_kb())

@router.message(StateFilter(CheckoutStates.collecting_phone), F.text == "✍️ Ввести вручную")
async def ask_phone_manual(message: Message, state: FSMContext) -> None:
    from aiogram.types import ReplyKeyboardRemove
    await state.set_state(CheckoutStates.collecting_phone_manual)
    await message.answer("Введите номер телефона:", reply_markup=ReplyKeyboardRemove())

@router.message(StateFilter(CheckoutStates.collecting_phone_manual))
async def collect_phone_manual(message: Message, state: FSMContext) -> None:
    phone = message.text.strip() if message.text else ""
    if len(phone) < 5:
        await message.answer("Похоже, номер телефона указан некорректно. Попробуйте снова.")
        return
    await state.update_data(phone=phone)
    await state.set_state(CheckoutStates.collecting_city)
    await message.answer("📍 Укажите город получения.", reply_markup=checkout_back_kb())

@router.message(StateFilter(CheckoutStates.collecting_city))
async def collect_city(message: Message, state: FSMContext) -> None:
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, укажите город.")
        return
    await state.update_data(city=message.text.strip())
    await state.set_state(CheckoutStates.collecting_pickup_point)
    await message.answer("🚚 Укажите адрес или номер пункта 5Post, куда будет доставлен заказ.", reply_markup=checkout_back_kb())

@router.message(StateFilter(CheckoutStates.collecting_pickup_point))
async def collect_pickup_point(message: Message, state: FSMContext) -> None:
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, укажите пункт 5Post.")
        return
    await state.update_data(pickup_point=message.text.strip())
    await state.set_state(CheckoutStates.collecting_comment)
    await message.answer("💬 Если хотите, оставьте комментарий к заказу.\n\nНапример: пожелания по упаковке или дополнительная информация.", reply_markup=skip_comment_kb())

@router.message(StateFilter(CheckoutStates.collecting_comment))
async def collect_comment(message: Message, state: FSMContext) -> None:
    await state.update_data(comment=message.text.strip() if message.text else None)
    await _show_preview(message, state)

@router.callback_query(F.data == "skip_comment", StateFilter(CheckoutStates.collecting_comment))
async def skip_comment(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(comment=None)
    await _show_preview(callback.message, state)
    await callback.answer()

# Куда возвращаться по «← Назад» с каждого шага оформления
_BACK_STEPS = {
    "CheckoutStates:collecting_phone": (CheckoutStates.collecting_name, "Как вас зовут?\n\nУкажите имя или ФИО."),
    "CheckoutStates:collecting_phone_manual": (CheckoutStates.collecting_phone, "📱 Укажите номер телефона для связи."),
    "CheckoutStates:collecting_city": (CheckoutStates.collecting_phone, "📱 Укажите номер телефона для связи."),
    "CheckoutStates:collecting_pickup_point": (CheckoutStates.collecting_city, "📍 Укажите город получения."),
    "CheckoutStates:collecting_comment": (CheckoutStates.collecting_pickup_point, "🚚 Укажите адрес или номер пункта 5Post, куда будет доставлен заказ."),
    "CheckoutStates:confirming_order": (CheckoutStates.collecting_comment, "💬 Если хотите, оставьте комментарий к заказу."),
}

@router.callback_query(F.data == "checkout_back")
async def checkout_back(callback: CallbackQuery, state: FSMContext) -> None:
    current = await state.get_state()
    prev = _BACK_STEPS.get(current)
    if not prev:
        await callback.answer("На этом шаге назад вернуться нельзя", show_alert=True)
        return
    new_state, text = prev
    await state.set_state(new_state)
    kb = None
    if new_state == CheckoutStates.collecting_phone:
        kb = phone_request_kb()
    elif new_state in (CheckoutStates.collecting_city, CheckoutStates.collecting_pickup_point):
        kb = checkout_back_kb()
    elif new_state == CheckoutStates.collecting_comment:
        kb = skip_comment_kb()
    await callback.message.answer(text, reply_markup=kb)
    await callback.answer()

async def _show_preview(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    order = await get_order_by_id(data["order_id"])
    lines = [
        "📋 <b>Проверьте данные</b>\n",
        f"ФИО: {html.escape(data['full_name'])}",
        f"Телефон: {html.escape(data['phone'])}",
        f"Город: {html.escape(data['city'])}",
        f"Пункт 5Post: {html.escape(data['pickup_point'])}",
        "",
        "Заказ:",
    ]
    for oi in order.items:
        lines.append(f"{oi.catalog_item.category.name}, фото №{oi.catalog_item.photo_number} — {oi.quantity} шт.")
    lines += ["", f"Стоимость растений: {order.plants_cost:.0f} ₽", f"Доставка: {order.delivery_cost:.0f} ₽", f"Итого: <b>{order.total_cost:.0f} ₽</b>", f"К оплате (полная предоплата): {order.prepayment:.0f} ₽"]
    await state.set_state(CheckoutStates.confirming_order)
    await message.answer("\n".join(lines), reply_markup=order_preview_kb(), parse_mode="HTML")

@router.callback_query(F.data == "confirm_order", StateFilter(CheckoutStates.confirming_order))
async def confirm_order(callback: CallbackQuery, state: FSMContext) -> None:
    from aiogram import Bot
    from db.crud import get_responsible_notify_ids
    data = await state.get_data()
    order_id = data["order_id"]
    order = await get_order_by_id(order_id)
    if not order or not order.items:
        await state.clear()
        await callback.answer("Корзина пуста — выберите растения в каталоге.", show_alert=True)
        return
    from db.crud import check_order_stock, reserve_stock_for_order
    problems = await check_order_stock(order_id)
    if problems:
        await callback.answer("⚠️ Не хватает остатков:\n" + "\n".join(problems) + "\n\nИзмените заказ.", show_alert=True)
        return
    await save_customer_data(order_id=order_id, full_name=data["full_name"], phone=data["phone"], city=data["city"], pickup_point=data["pickup_point"], comment=data.get("comment"))
    await save_user_contact_data(callback.from_user.id, data["full_name"], data["phone"], data["city"], data["pickup_point"])
    await reserve_stock_for_order(order_id)
    await update_order_status(order_id, OrderStatus.AWAITING_PREPAYMENT)
    await log("order_confirmed", user_id=callback.from_user.id, order_id=order_id)
    await state.clear()
    order = await get_order_by_id(order_id)
    from config import WEBAPP_URL
    from db.crud import ensure_pay_token, get_payment_requisites, format_requisites_text
    pay_token = await ensure_pay_token(order_id)
    pay_url = f"{WEBAPP_URL}/pay/{pay_token}" if WEBAPP_URL and pay_token else None
    requisites = format_requisites_text(await get_payment_requisites())
    await callback.message.answer(f"✅ *Заявка создана*\n\nВаш номер заказа: *№{order.id}*\n\nСтатус: Ожидается оплата", parse_mode="Markdown")
    from keyboards.checkout_kb import prepayment_kb
    await callback.message.answer(f"💳 *Оплата заказа*\n\nСумма вашего заказа: {order.total_cost:.0f} ₽\nОплачивается полностью: {order.prepayment:.0f} ₽\n\nДля бронирования переведите {order.prepayment:.0f} ₽ на реквизиты:\n\n{requisites}\n\nПосле оплаты отправьте чек кнопкой ниже.", reply_markup=prepayment_kb(pay_url), parse_mode="Markdown")
    admin_text = (
        f"🔔 <b>Новый заказ №{order.id}</b>\n\n"
        f"Клиент: {html.escape(order.full_name or '')}\nТелефон: {html.escape(order.phone or '')}\nГород: {html.escape(order.city or '')}\n"
        f"Пункт 5Post: {html.escape(order.pickup_point or '')}\n\nИтого: {order.total_cost:.0f} ₽\nК оплате полностью: {order.prepayment:.0f} ₽\n\n"
        f"Статус: ожидается оплата"
    )
    bot: Bot = callback.bot
    for admin_id in await get_responsible_notify_ids(order.user_id, order_employee_id=order.employee_id):
        try:
            await bot.send_message(admin_id, admin_text, parse_mode="HTML")
        except Exception:
            pass
    from services.export import send_export_to_admin
    await send_export_to_admin(bot, caption=f"📊 Выгрузка обновлена: новый заказ №{order.id}")
    await callback.answer()

@router.callback_query(F.data == "edit_customer_data", StateFilter(CheckoutStates.confirming_order))
async def edit_customer_data(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CheckoutStates.collecting_name)
    await callback.message.answer("Как вас зовут?\n\nУкажите имя или ФИО.", reply_markup=checkout_cancel_kb())
    await callback.answer()


@router.callback_query(F.data == "cancel_checkout")
async def cancel_checkout(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    order_id = data.get("order_id")
    await state.clear()
    if order_id:
        await log("checkout_cancelled", user_id=callback.from_user.id, order_id=order_id)
    await callback.answer("Оформление отменено")
    from handlers.cart import show_cart
    await show_cart(callback)

@router.callback_query(F.data == "order_template")
async def show_template(callback: CallbackQuery) -> None:
    template = "ЗАЯВКА\n\nИмя / ФИО:\nТелефон:\nГород:\nПункт 5Post:\n\nЗаказ:\nФото №__ — __ шт.\nФото №__ — __ шт.\nФото №__ — __ шт.\n\nКомментарий:"
    await callback.message.answer(f"```\n{template}\n```", parse_mode="Markdown")
    await callback.answer()
