from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from config import DATABASE_URL
from db.models import Base

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def init_db() -> None:
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_run_migrations)
    await _seed_initial_data()

def _run_migrations(conn) -> None:
    """Лёгкие миграции SQLite: добавление новых колонок в существующие таблицы."""
    from sqlalchemy import text
    new_columns = {
        "catalog_items": [
            ("kind", "VARCHAR(32) NOT NULL DEFAULT 'product'"),
            ("title", "VARCHAR(256)"),
        ],
        "users": [
            ("pickup_point", "VARCHAR(512)"),
            ("employee_id", "INTEGER REFERENCES employees(id)"),
            ("source", "VARCHAR(32) DEFAULT 'bot'"),
            ("chat_token", "VARCHAR(64)"),
        ],
        "orders": [
            ("employee_id", "INTEGER REFERENCES employees(id)"),
            ("source", "VARCHAR(32)"),
            ("pay_token", "VARCHAR(64)"),
            ("prepayment_paid_at", "DATETIME"),
            ("remainder_paid_at", "DATETIME"),
        ],
        "payments": [
            ("kind", "VARCHAR(16) NOT NULL DEFAULT 'prepayment'"),
            ("receipt_hash", "VARCHAR(64)"),
            ("operation_id", "VARCHAR(128)"),
            ("check_status", "VARCHAR(16) NOT NULL DEFAULT 'needs_review'"),
            ("check_details", "TEXT"),
            ("paid_at", "DATETIME"),
        ],
        "employees": [
            ("username", "VARCHAR(128)"),
            ("password_hash", "VARCHAR(256)"),
            ("secret_token", "VARCHAR(128)"),
            ("role", "VARCHAR(32) DEFAULT 'manager'"),
            ("last_login_at", "DATETIME"),
        ],
    }
    for table, columns in new_columns.items():
        existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
        for name, ddl in columns:
            if name not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
    # Уникальный индекс для токена страницы оплаты (ALTER TABLE не умеет UNIQUE)
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_orders_pay_token ON orders (pay_token)"))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_chat_token ON users (chat_token)"))
    _rebuild_users_if_needed(conn)

def _rebuild_users_if_needed(conn) -> None:
    """Снимает NOT NULL с users.telegram_id (SQLite не умеет ALTER COLUMN — пересоздаём таблицу).

    Нужно для клиентов сайта, у которых нет Telegram-аккаунта.
    """
    from sqlalchemy import text
    info = {row[1]: row for row in conn.execute(text("PRAGMA table_info(users)"))}
    tg_col = info.get("telegram_id")
    if not tg_col or not tg_col[3]:  # колонки нет или NOT NULL уже снят
        return
    conn.execute(text(
        "CREATE TABLE users_new ("
        "id INTEGER PRIMARY KEY, "
        "telegram_id INTEGER, "
        "username VARCHAR(64), "
        "full_name VARCHAR(256), "
        "phone VARCHAR(32), "
        "city VARCHAR(128), "
        "pickup_point VARCHAR(512), "
        "employee_id INTEGER REFERENCES employees(id), "
        "source VARCHAR(32) DEFAULT 'bot', "
        "chat_token VARCHAR(64), "
        "created_at DATETIME)"
    ))
    conn.execute(text(
        "INSERT INTO users_new "
        "SELECT id, telegram_id, username, full_name, phone, city, pickup_point, employee_id, source, chat_token, created_at "
        "FROM users"
    ))
    conn.execute(text("DROP TABLE users"))
    conn.execute(text("ALTER TABLE users_new RENAME TO users"))
    conn.execute(text("CREATE UNIQUE INDEX ix_users_telegram_id ON users (telegram_id)"))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_chat_token ON users (chat_token)"))

async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

async def _seed_initial_data() -> None:
    from db.crud import get_setting, set_setting, get_categories, create_category
    from config import DEFAULT_DELIVERY_COST, DEFAULT_PAYMENT_REQUISITES, DEFAULT_PICKUP_ADDRESS
    if not await get_setting("delivery_cost"):
        await set_setting("delivery_cost", str(DEFAULT_DELIVERY_COST))
    if not await get_setting("payment_requisites"):
        await set_setting("payment_requisites", DEFAULT_PAYMENT_REQUISITES)
    # Структурированные реквизиты (пустые — пока админ не заполнит; fallback — payment_requisites)
    for key in ("payment_card", "payment_phone_sbp", "payment_wallet", "payment_recipient_name"):
        if await get_setting(key) is None:
            await set_setting(key, "")
    if not await get_setting("pickup_address"):
        await set_setting("pickup_address", DEFAULT_PICKUP_ADDRESS)
    if not await get_setting("manager_contact"):
        await set_setting("manager_contact", "@DanilLysenko")
    existing = await get_categories()
    if existing:
        return
    initial_categories = [
        {"name": "Пионы", "slug": "pion", "default_price": 350, "sort_order": 1},
        {"name": "Лилии", "slug": "lily", "default_price": 100, "sort_order": 2},
        {"name": "Флоксы", "slug": "phlox", "default_price": 200, "sort_order": 3},
        {"name": "Хосты", "slug": "hosta", "default_price": 250, "sort_order": 4},
        {"name": "Гортензия метельчатая", "slug": "hydrangea", "default_price": 300, "sort_order": 5},
        {"name": "Хризантема мультифлора", "slug": "chrysanthemum", "default_price": 180, "sort_order": 6},
        {"name": "Декоративный лук", "slug": "allium", "default_price": 120, "sort_order": 7},
    ]
    for cat in initial_categories:
        await create_category(**cat)
