from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from db.crud import get_categories, get_category_by_slug, get_category_items, get_or_create_draft, add_item_to_cart, get_setting
from keyboards.catalog_kb import category_list_kb, category_card_kb, photo_carousel_kb, items_grid_kb, PAGE_SIZE
from states.states import CatalogStates
from services.logger import log

router = Router()

CATEGORY_INFO = {"pion": "Многолетние, зимостойкие\nОКС / ЗКС\nОтправка 5Post", "lily": "Многолетние, морозостойкие\nВыкапывать на зиму не нужно\nСредняя высота — 1 м 15 см", "phlox": "Многолетние, морозостойкие\nВысота до 1 метра", "hosta": "Саженец", "hydrangea": "Саженец", "chrysanthemum": "Саженец", "allium": "Луковица"}


async def _safe_delete(message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


@router.callback_query(F.data == "catalog")
async def show_catalog(callback: CallbackQuery) -> None:
    categories = await get_categories()
    cover = await get_setting("catalog_cover_file_id")
    caption = "🌿 *Каталог растений*\n\nВыберите категорию:"
    kb = category_list_kb(categories)
    if cover:
        await callback.message.answer_photo(photo=cover, caption=caption, reply_markup=kb, parse_mode="Markdown")
    else:
        await callback.message.answer(caption, reply_markup=kb, parse_mode="Markdown")
    await _safe_delete(callback.message)
    await callback.answer()

@router.callback_query(F.data.startswith("cat_"))
async def show_category_card(callback: CallbackQuery) -> None:
    slug = callback.data.replace("cat_", "")
    category = await get_category_by_slug(slug)
    if not category:
        await callback.answer("Категория не найдена", show_alert=True)
        return
    info = CATEGORY_INFO.get(slug, "")
    caption = f"🌸 *{category.name}*\n\n{info}\n\n💰 {category.default_price:.0f} ₽ / шт."
    saplings = await get_category_items(slug, kind="sapling")
    kb = category_card_kb(slug, has_saplings=bool(saplings))
    if category.infographic_file_id:
        await callback.message.answer_photo(photo=category.infographic_file_id, caption=caption, reply_markup=kb, parse_mode="Markdown")
    else:
        await callback.message.answer(caption, reply_markup=kb, parse_mode="Markdown")
    await _safe_delete(callback.message)
    await callback.answer()

@router.callback_query(F.data.startswith("saplings_"))
async def show_saplings(callback: CallbackQuery) -> None:
    slug = callback.data.replace("saplings_", "")
    items = await get_category_items(slug, kind="sapling")
    if not items:
        await callback.answer("Фото саженцев пока нет", show_alert=True)
        return
    media = [InputMediaPhoto(media=i.file_id) for i in items[:10] if i.file_id]
    if media:
        media[0].caption = "🌱 Так выглядит посадочный материал (саженец/луковица), который вы получите."
        await callback.message.answer_media_group(media=media)
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌸 Смотреть позиции", callback_data=f"view_items_{slug}")],
        [InlineKeyboardButton(text="← Назад к категории", callback_data=f"cat_{slug}")],
    ])
    await callback.message.answer("Цветущие растения — в позициях каталога:", reply_markup=back_kb)
    await callback.answer()

@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.startswith("view_items_"))
async def show_items(callback: CallbackQuery) -> None:
    slug = callback.data.replace("view_items_", "")
    await _show_items_page(callback, slug, 0)

@router.callback_query(F.data.startswith("items_page_"))
async def show_items_page(callback: CallbackQuery) -> None:
    slug, page_str = callback.data.replace("items_page_", "").rsplit("_", 1)
    await _show_items_page(callback, slug, int(page_str))

async def _show_items_page(callback: CallbackQuery, slug: str, page: int) -> None:
    items = await get_category_items(slug, kind="product")
    if not items:
        await callback.answer("Позиций пока нет", show_alert=True)
        return
    total_pages = (len(items) + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))
    page_items = items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    media = []
    for it in page_items:
        if not it.file_id:
            continue
        title = f"{it.title} · " if it.title else ""
        caption = f"{title}№{it.photo_number} — {it.price:.0f} ₽ · в наличии {it.stock} шт."
        media.append(InputMediaPhoto(media=it.file_id, caption=caption))
    if media:
        await callback.message.answer_media_group(media=media)
    await callback.message.answer(
        "🔢 *Выберите позицию по номеру:*",
        reply_markup=items_grid_kb(slug, items, page),
        parse_mode="Markdown",
    )
    await _safe_delete(callback.message)
    await callback.answer()

@router.callback_query(F.data.startswith("item_"))
async def show_item_card(callback: CallbackQuery, state: FSMContext) -> None:
    slug, idx_str = callback.data.replace("item_", "").rsplit("_", 1)
    idx = int(idx_str)
    items = await get_category_items(slug, kind="product")
    if not (0 <= idx < len(items)):
        await callback.answer("Позиция не найдена", show_alert=True)
        return
    await state.update_data(slug=slug, idx=idx, qty=1)
    await state.set_state(CatalogStates.viewing_photos)
    await _render_photo(callback, items, idx, 1, slug)

@router.callback_query(F.data.startswith("photo_next_") | F.data.startswith("photo_prev_"))
async def switch_photo(callback: CallbackQuery, state: FSMContext) -> None:
    direction, slug, idx_str = _parse_nav(callback.data)
    idx = int(idx_str)
    new_idx = idx + 1 if "next" in callback.data else idx - 1
    items = await get_category_items(slug, kind="product")
    if not (0 <= new_idx < len(items)):
        await callback.answer()
        return
    await state.update_data(idx=new_idx, qty=1)
    await _render_photo(callback, items, new_idx, 1, slug, edit=True)

@router.callback_query(F.data.startswith("qty_inc_") | F.data.startswith("qty_dec_"))
async def change_quantity(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split("_")
    action, slug, idx = parts[1], parts[2], int(parts[3])
    data = await state.get_data()
    qty = data.get("qty", 1)
    qty = qty + 1 if action == "inc" else max(1, qty - 1)
    await state.update_data(qty=qty)
    items = await get_category_items(slug, kind="product")
    await _render_photo(callback, items, idx, qty, slug, edit=True)

@router.callback_query(F.data.startswith("add_to_cart_"))
async def add_to_cart(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.replace("add_to_cart_", "").rsplit("_", 1)
    slug, idx_str = parts[0], parts[1]
    idx = int(idx_str)
    data = await state.get_data()
    qty = data.get("qty", 1)
    items = await get_category_items(slug, kind="product")
    if not (0 <= idx < len(items)):
        await callback.answer("Позиция не найдена", show_alert=True)
        return
    item = items[idx]
    order = await get_or_create_draft(callback.from_user.id, callback.from_user.username)
    added = await add_item_to_cart(order.id, item.id, qty)
    if added == 0:
        await callback.answer("❌ Свободного остатка нет — всё уже в вашем заказе.", show_alert=True)
        return
    await log("cart_item_added", user_id=callback.from_user.id, order_id=order.id, details=f"{slug} photo#{item.photo_number} x{added}")
    if added < qty:
        await callback.answer(f"✅ Добавлено: {added} шт. (больше нет в наличии)", show_alert=True)
    else:
        await callback.answer(f"✅ Добавлено: {added} шт.", show_alert=False)

def _parse_nav(data: str):
    prefix = "photo_next_" if data.startswith("photo_next_") else "photo_prev_"
    rest = data.replace(prefix, "")
    slug, idx_str = rest.rsplit("_", 1)
    return prefix, slug, idx_str

async def _render_photo(callback: CallbackQuery, items, idx: int, qty: int, slug: str, edit: bool = False) -> None:
    import html
    item = items[idx]
    name = html.escape(item.title) if item.title else f"Фото №{item.photo_number}"
    category_name = html.escape(item.category.name)
    caption = (
        f"🌸 <b>{category_name}</b> · позиция {idx + 1} из {len(items)}\n"
        f"{name}\n\n"
        f"<b>{item.price:.0f} ₽</b> / шт.\n"
        f"{'✅ В наличии: ' + str(item.stock) + ' шт.' if item.stock > 0 else '❌ Нет в наличии'}"
    )
    kb = photo_carousel_kb(idx, len(items), qty, slug)
    if edit and item.file_id:
        try:
            await callback.message.edit_media(media=InputMediaPhoto(media=item.file_id, caption=caption, parse_mode="HTML"), reply_markup=kb)
            await callback.answer()
            return
        except TelegramBadRequest:
            pass
    if item.file_id:
        await callback.message.answer_photo(photo=item.file_id, caption=caption, reply_markup=kb, parse_mode="HTML")
    else:
        await callback.message.answer(caption, reply_markup=kb, parse_mode="HTML")
    if not edit:
        await _safe_delete(callback.message)
    await callback.answer()
