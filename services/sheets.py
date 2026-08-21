"""Интеграция с Google Sheets."""
from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from db.models import Order

HEADERS = ["ID заказа", "Дата", "Время", "Telegram ID", "Username", "ФИО", "Телефон", "Город", "Пункт 5Post", "Состав заказа", "Стоимость растений", "Доставка", "Итого", "Предоплата", "Остаток", "Чек", "Статус", "Трек-номер", "Комментарий"]

def _get_sheet():
    try:
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials
        from config import GOOGLE_CREDENTIALS_FILE, GOOGLE_SHEETS_ID
        if not GOOGLE_SHEETS_ID:
            return None
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        sh = client.open_by_key(GOOGLE_SHEETS_ID)
        worksheet = sh.sheet1
        if not worksheet.row_values(1):
            worksheet.append_row(HEADERS)
        return worksheet
    except Exception as exc:
        print(f"[sheets] Ошибка: {exc}")
        return None

async def save_order_to_sheets(order: "Order") -> None:
    def _sync_save():
        sheet = _get_sheet()
        if not sheet:
            return
        items_str = "; ".join(f"{oi.catalog_item.category.name} фото №{oi.catalog_item.photo_number} × {oi.quantity} шт. по {oi.price_at_order:.0f}₽" for oi in order.items)
        row = [order.id, str(order.created_at.date()), str(order.created_at.time().strftime("%H:%M")), order.user.telegram_id, order.user.username or "", order.full_name or "", order.phone or "", order.city or "", order.pickup_point or "", items_str, order.plants_cost, order.delivery_cost, order.total_cost, order.prepayment, order.remainder, order.receipt_file_id or "", order.status.value, order.track_number or "", order.comment or ""]
        try:
            sheet.append_row(row)
        except Exception as exc:
            print(f"[sheets] Ошибка сохранения: {exc}")
    await asyncio.get_event_loop().run_in_executor(None, _sync_save)

async def update_order_status_in_sheets(order_id: int, status: str) -> None:
    def _sync_update():
        sheet = _get_sheet()
        if not sheet:
            return
        try:
            cell = sheet.find(str(order_id), in_column=1)
            if cell:
                status_col = HEADERS.index("Статус") + 1
                sheet.update_cell(cell.row, status_col, status)
        except Exception as exc:
            print(f"[sheets] Ошибка обновления: {exc}")
    await asyncio.get_event_loop().run_in_executor(None, _sync_update)
