from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from db.crud import (
    assign_employee_to_user,
    get_draft_order,
    get_employee_by_ref_code,
    get_employee_by_telegram_id,
    get_or_create_user,
    get_setting,
    log_referral_event,
)
from keyboards.main_menu import main_menu_kb
from services.logger import log

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    user = message.from_user
    db_user = await get_or_create_user(user.id, user.username)
    employee = None
    # Реферальная ссылка сотрудника: /start ref_<code> — первый источник побеждает
    if command.args and command.args.startswith("ref_"):
        ref_code = command.args[4:]
        employee = await get_employee_by_ref_code(ref_code)
        if employee:
            await assign_employee_to_user(db_user.id, employee.id)
            await log_referral_event(employee_id=employee.id, source="bot", user_id=db_user.id)
            await log("referral_attached", user_id=user.id, details=f"employee={employee.ref_code}")
    draft = await get_draft_order(user.id)
    await log("start", user_id=user.id)
    is_employee = bool(await get_employee_by_telegram_id(user.id))
    welcome_file_id = await get_setting("welcome_cover_file_id")
    text = "🌸 *Питомник многолетников*\n\nЗдесь можно посмотреть растения, узнать условия доставки и оформить заказ.\n\nВыберите нужный раздел:"
    if draft:
        text += f"\n\n⚠️ У вас есть незавершённый заказ *№{draft.id}*."
    kb = main_menu_kb(has_draft=bool(draft), is_employee=is_employee)
    if welcome_file_id:
        await message.answer_photo(photo=welcome_file_id, caption=text, reply_markup=kb, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    draft = await get_draft_order(message.from_user.id)
    await message.answer("↩️ Действие отменено.\n\nВы в главном меню:", reply_markup=main_menu_kb(has_draft=bool(draft)))

@router.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    draft = await get_draft_order(callback.from_user.id)
    is_employee = bool(await get_employee_by_telegram_id(callback.from_user.id))
    text = "🌸 *Главное меню*\n\nВыберите нужный раздел:"
    try:
        await callback.message.edit_text(text, reply_markup=main_menu_kb(has_draft=bool(draft), is_employee=is_employee), parse_mode="Markdown")
    except TelegramBadRequest:
        # Текущее сообщение — фото/медиа, текст отредактировать нельзя
        await callback.message.answer(text, reply_markup=main_menu_kb(has_draft=bool(draft), is_employee=is_employee), parse_mode="Markdown")
        await callback.message.delete()
    await callback.answer()

@router.callback_query(F.data == "resume_order")
async def resume_order(callback: CallbackQuery) -> None:
    from handlers.cart import show_cart
    await show_cart(callback)
