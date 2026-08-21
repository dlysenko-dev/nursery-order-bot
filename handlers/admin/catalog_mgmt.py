from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message
from config import ADMIN_IDS
from db.crud import get_categories, get_category_items, set_item_price, set_item_stock, toggle_item_active, create_catalog_item, update_category_infographic
from keyboards.admin_kb import admin_back_kb
from states.states import AdminStates

router = Router()

def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@router.callback_query(F.data == "admin_items")
async def show_categories_for_mgmt(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    categories = await get_categories(active_only=False)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = [[InlineKeyboardButton(text=c.name, callback_data=f"admin_cat_items_{c.slug}")] for c in categories]
    buttons.append([InlineKeyboardButton(text="← Назад", callback_data="admin_main")])
    await callback.message.edit_text("🌱 Выберите категорию для управления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@router.callback_query(F.data.startswith("admin_cat_items_"))
async def show_items_for_category(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    slug = callback.data.replace("admin_cat_items_", "")
    items = await get_category_items(slug, active_only=False)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = [[InlineKeyboardButton(text=f"Фото №{i.photo_number} | {i.price:.0f}₽ | остаток {i.stock} | {'✅' if i.is_active else '🚫'}", callback_data=f"admin_toggle_item_{i.id}")] for i in items]
    buttons.append([InlineKeyboardButton(text="➕ Добавить позицию", callback_data=f"admin_add_item_{slug}")])
    buttons.append([InlineKeyboardButton(text="← Назад", callback_data="admin_items")])
    await callback.message.edit_text("Позиции категории (нажмите, чтобы включить/выключить):", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@router.callback_query(F.data.startswith("admin_toggle_item_"))
async def toggle_item(callback: CallbackQuery) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    item_id = int(callback.data.replace("admin_toggle_item_", ""))
    new_state = await toggle_item_active(item_id)
    await callback.answer(f"Позиция теперь {'активна' if new_state else 'отключена'}")

@router.callback_query(F.data.startswith("admin_add_item_"))
async def start_add_item(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    slug = callback.data.replace("admin_add_item_", "")
    await state.update_data(slug=slug)
    await state.set_state(AdminStates.waiting_photo_upload)
    await callback.message.answer("Отправьте фотографию новой позиции:")
    await callback.answer()

@router.message(StateFilter(AdminStates.waiting_photo_upload), F.photo)
async def receive_new_photo(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    file_id = message.photo[-1].file_id
    await state.update_data(file_id=file_id)
    await state.set_state(AdminStates.waiting_photo_number)
    await message.answer("Введите номер фото (например 5):")

@router.message(StateFilter(AdminStates.waiting_photo_number))
async def receive_photo_number(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.update_data(photo_number=int(message.text.strip()))
    await state.set_state(AdminStates.waiting_item_price)
    await message.answer("Введите цену (в рублях):")

@router.message(StateFilter(AdminStates.waiting_item_price))
async def receive_item_price(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    await state.update_data(price=float(message.text.strip()))
    await state.set_state(AdminStates.waiting_item_stock)
    await message.answer("Введите остаток (количество в наличии):")

@router.message(StateFilter(AdminStates.waiting_item_stock))
async def receive_item_stock(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    stock = int(message.text.strip())
    await create_catalog_item(category_slug=data["slug"], photo_number=data["photo_number"], price=data["price"], stock=stock, file_id=data["file_id"])
    await state.clear()
    await message.answer("✅ Новая позиция добавлена в каталог.")

@router.callback_query(F.data.startswith("admin_upload_infographic_"))
async def start_upload_infographic(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    slug = callback.data.replace("admin_upload_infographic_", "")
    await state.update_data(slug=slug)
    await state.set_state(AdminStates.waiting_infographic_upload)
    await callback.message.answer("Отправьте изображение-инфографику для категории:")
    await callback.answer()

@router.message(StateFilter(AdminStates.waiting_infographic_upload), F.photo)
async def receive_infographic(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    file_id = message.photo[-1].file_id
    await update_category_infographic(data["slug"], file_id)
    await state.clear()
    await message.answer("✅ Инфографика категории обновлена.")
