from __future__ import annotations
import enum
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, relationship

class Base(DeclarativeBase):
    pass

class OrderStatus(str, enum.Enum):
    DRAFT = "Черновик"
    PLACED = "Оформлен"
    AWAITING_PREPAYMENT = "Ожидается предоплата"
    RECEIPT_RECEIVED = "Чек получен"
    ON_REVIEW = "На проверке"
    PAYMENT_CONFIRMED = "Оплата подтверждена"
    ORDER_CONFIRMED = "Заказ подтверждён"
    PREPARING = "Готовится к отправке"
    SHIPPED = "Отправлен"
    COMPLETED = "Завершён"
    CANCELLED = "Отменён"

class Employee(Base):
    """Сотрудник со своей реферальной ссылкой — ведёт учёт привлечённых клиентов."""
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=True, index=True)
    name = Column(String(128), nullable=False)
    ref_code = Column(String(64), unique=True, nullable=False)
    username = Column(String(128), unique=True, nullable=True)
    password_hash = Column(String(256), nullable=True)
    secret_token = Column(String(128), unique=True, nullable=True)
    role = Column(String(32), nullable=False, default="manager")  # admin | manager
    is_active = Column(Boolean, default=True)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class EmployeeSession(Base):
    """Сессия сотрудника для входа на сайт по логину/паролю."""
    __tablename__ = "employee_sessions"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    token = Column(String(128), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_agent = Column(String(512), nullable=True)
    ip = Column(String(64), nullable=True)


class ReferralEvent(Base):
    """Событие перехода по реферальной ссылке (для статистики менеджера)."""
    __tablename__ = "referral_events"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    source = Column(String(32), nullable=False)  # bot | miniapp | site
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_agent = Column(String(512), nullable=True)
    ip = Column(String(64), nullable=True)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=True, index=True)  # NULL — клиент сайта без Telegram
    username = Column(String(64), nullable=True)
    full_name = Column(String(256), nullable=True)
    phone = Column(String(32), nullable=True)
    city = Column(String(128), nullable=True)
    pickup_point = Column(String(512), nullable=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)  # кто привёл клиента
    source = Column(String(32), nullable=True, default="bot")  # bot | miniapp | site
    site_token = Column(String(64), unique=True, nullable=True)  # персональная ссылка/сессия клиента сайта
    created_at = Column(DateTime, default=datetime.utcnow)
    orders = relationship("Order", back_populates="user", lazy="selectin")
    employee = relationship("Employee")


class ChatMessage(Base):
    """Единый чат клиент↔менеджер: сообщения с сайта и из бота хранятся вместе."""
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)  # контекст заказа, если есть
    sender = Column(String(16), nullable=False)  # client | manager
    text = Column(Text, nullable=False)
    via = Column(String(16), nullable=False, default="site")  # site | bot — откуда отправлено
    created_at = Column(DateTime, default=datetime.utcnow)
    read_by_manager = Column(Boolean, default=False)
    read_by_client = Column(Boolean, default=False)
    user = relationship("User", lazy="selectin")

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    slug = Column(String(64), unique=True, nullable=False)
    infographic_file_id = Column(String(256), nullable=True)
    description = Column(Text, nullable=True)
    default_price = Column(Float, nullable=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    items = relationship("CatalogItem", back_populates="category", lazy="selectin")

class CatalogItem(Base):
    __tablename__ = "catalog_items"
    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    photo_number = Column(Integer, nullable=False)
    file_id = Column(String(256), nullable=True)
    title = Column(String(256), nullable=True)
    kind = Column(String(32), nullable=False, default="product")  # product | sapling
    price = Column(Float, nullable=False)
    stock = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    category = relationship("Category", back_populates="items", lazy="selectin")
    order_items = relationship("OrderItem", back_populates="catalog_item")

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(Enum(OrderStatus), default=OrderStatus.DRAFT, nullable=False)
    full_name = Column(String(256), nullable=True)
    phone = Column(String(32), nullable=True)
    city = Column(String(128), nullable=True)
    pickup_point = Column(String(512), nullable=True)
    comment = Column(Text, nullable=True)
    plants_cost = Column(Float, default=0.0)
    delivery_cost = Column(Float, default=300.0)
    total_cost = Column(Float, default=0.0)
    prepayment = Column(Float, default=0.0)
    remainder = Column(Float, default=0.0)
    receipt_file_id = Column(String(256), nullable=True)
    track_number = Column(String(128), nullable=True)
    admin_comment = Column(Text, nullable=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)  # денормализация: чей клиент
    source = Column(String(32), nullable=True)  # bot | miniapp | site
    pay_token = Column(String(64), unique=True, nullable=True)  # токен публичной страницы оплаты /pay/<token>
    prepayment_paid_at = Column(DateTime, nullable=True)  # когда подтверждена предоплата
    remainder_paid_at = Column(DateTime, nullable=True)  # когда подтверждён остаток
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("User", back_populates="orders", lazy="selectin")
    items = relationship("OrderItem", back_populates="order", lazy="selectin", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="order", lazy="selectin")

class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    catalog_item_id = Column(Integer, ForeignKey("catalog_items.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    price_at_order = Column(Float, nullable=False)
    order = relationship("Order", back_populates="items")
    catalog_item = relationship("CatalogItem", back_populates="order_items", lazy="selectin")

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    amount = Column(Float, nullable=False)
    receipt_file_id = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    verified = Column(Boolean, nullable=True)
    kind = Column(String(16), nullable=False, default="prepayment")  # prepayment | remainder
    receipt_hash = Column(String(64), nullable=True)  # sha256 файла чека (анти-повтор)
    operation_id = Column(String(128), nullable=True)  # номер операции из чека (анти-повтор)
    check_status = Column(String(16), nullable=False, default="needs_review")  # auto_approved | needs_review | rejected
    check_details = Column(Text, nullable=True)  # JSON с результатами автопроверки
    paid_at = Column(DateTime, nullable=True)  # дата/время оплаты из чека
    order = relationship("Order", back_populates="payments")

class EventLog(Base):
    __tablename__ = "event_logs"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    user_telegram_id = Column(Integer, nullable=True)
    event = Column(String(128), nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Settings(Base):
    __tablename__ = "settings"
    key = Column(String(64), primary_key=True)
    value = Column(String(512), nullable=True)
