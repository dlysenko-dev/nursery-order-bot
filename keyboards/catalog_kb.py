from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

PAGE_SIZE = 10

def category_list_kb(categories) -> InlineKeyboardMarkup:
    # по 2 категории в ряд — компактнее и нагляднее
    rows = []
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(text=cat.name, callback_data=f"cat_{cat.slug}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def category_card_kb(slug: str, has_saplings: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🌸 Смотреть позиции", callback_data=f"view_items_{slug}")],
    ]
    if has_saplings:
        buttons.append([InlineKeyboardButton(text="🌱 Как выглядит саженец", callback_data=f"saplings_{slug}")])
    buttons += [
        [InlineKeyboardButton(text="🛒 Перейти к заказу", callback_data="cart")],
        [InlineKeyboardButton(text="← Назад", callback_data="catalog")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def items_grid_kb(slug: str, items, page: int) -> InlineKeyboardMarkup:
    """Сетка номеров позиций текущей страницы + навигация по страницам."""
    start = page * PAGE_SIZE
    page_items = items[start:start + PAGE_SIZE]
    rows = []
    row = []
    for i, item in enumerate(page_items):
        idx = start + i
        row.append(InlineKeyboardButton(text=f"№{item.photo_number}", callback_data=f"item_{slug}_{idx}"))
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    total_pages = (len(items) + PAGE_SIZE - 1) // PAGE_SIZE
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="‹", callback_data=f"items_page_{slug}_{page - 1}"))
        nav.append(InlineKeyboardButton(text=f"{start + 1}–{start + len(page_items)} из {len(items)}", callback_data="noop"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="›", callback_data=f"items_page_{slug}_{page + 1}"))
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="← Назад к категории", callback_data=f"cat_{slug}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def photo_carousel_kb(idx: int, total: int, qty: int, slug: str) -> InlineKeyboardMarkup:
    qty_row = [
        InlineKeyboardButton(text="➖", callback_data=f"qty_dec_{slug}_{idx}"),
        InlineKeyboardButton(text=f"{qty} шт.", callback_data="noop"),
        InlineKeyboardButton(text="➕", callback_data=f"qty_inc_{slug}_{idx}"),
    ]
    nav_row = []
    if idx > 0:
        nav_row.append(InlineKeyboardButton(text="‹ Предыдущая", callback_data=f"photo_prev_{slug}_{idx}"))
    if idx < total - 1:
        nav_row.append(InlineKeyboardButton(text="Следующая ›", callback_data=f"photo_next_{slug}_{idx}"))
    rows = [qty_row, [InlineKeyboardButton(text="🛒 Добавить в заказ", callback_data=f"add_to_cart_{slug}_{idx}")]]
    rows.append([InlineKeyboardButton(text="🛒 Перейти к заказу", callback_data="cart")])
    if nav_row:
        rows.append(nav_row)
    rows.append([InlineKeyboardButton(text="← К списку позиций", callback_data=f"view_items_{slug}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
