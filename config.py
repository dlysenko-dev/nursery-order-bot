import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

_admin_ids_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: list[int] = [
    int(x.strip()) for x in _admin_ids_raw.split(",") if x.strip().isdigit()
]

DEFAULT_DELIVERY_COST: float = float(os.getenv("DELIVERY_COST", "300"))
DEFAULT_PREPAYMENT_PERCENT: int = 100
DEFAULT_PAYMENT_REQUISITES: str = os.getenv(
    "PAYMENT_REQUISITES", "Ozon Банк: 89233981917"
)
DEFAULT_PICKUP_ADDRESS: str = os.getenv("PICKUP_ADDRESS", "")

DATABASE_URL: str = os.getenv(
    "DATABASE_URL", "sqlite+aiosqlite:///plant_shop.db"
)

GOOGLE_SHEETS_ID: str = os.getenv("GOOGLE_SHEETS_ID", "")
GOOGLE_CREDENTIALS_FILE: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

# Веб-слой: сайт + Telegram Mini App
WEBAPP_URL: str = os.getenv("WEBAPP_URL", "")
WEB_PORT: int = int(os.getenv("WEB_PORT", "8000"))
BOT_USERNAME: str = os.getenv("BOT_USERNAME", "").lstrip("@")
WEBAPP_SHORT_NAME: str = os.getenv("WEBAPP_SHORT_NAME", "")
