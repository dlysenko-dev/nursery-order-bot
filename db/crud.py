"""CRUD-операции. Все функции — async."""
from __future__ import annotations
import secrets
from datetime import datetime
from typing import Optional
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import AsyncSessionLocal
from db.models import CatalogItem, Category, ChatMessage, Employee, EmployeeSession, EventLog, Order, OrderItem, OrderStatus, Payment, ReferralEvent, Settings, User

async def get_setting(key: str) -> Optional[str]:
    async with AsyncSessionLocal() as s:
        row = await s.get(Settings, key)
        return row.value if row else None

async def set_setting(key: str, value: str) -> None:
    async with AsyncSessionLocal() as s:
        row = await s.get(Settings, key)
        if row:
            row.value = value
        else:
            s.add(Settings(key=key, value=value))
        await s.commit()

async def get_or_create_user(telegram_id: int, username: str | None) -> User:
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            user = User(telegram_id=telegram_id, username=username)
            s.add(user)
        if not user.site_token:
            user.site_token = secrets.token_urlsafe(16)
        await s.commit()
        await s.refresh(user)
        return user

async def get_categories(active_only: bool = True) -> list[Category]:
    async with AsyncSessionLocal() as s:
        q = select(Category).order_by(Category.sort_order)
        if active_only:
            q = q.where(Category.is_active.is_(True))
        result = await s.execute(q)
        return list(result.scalars().all())

async def get_category_by_slug(slug: str) -> Optional[Category]:
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(Category).where(Category.slug == slug))
        return result.scalar_one_or_none()

async def create_category(name: str, slug: str, default_price: float, sort_order: int = 0, description: str | None = None) -> Category:
    async with AsyncSessionLocal() as s:
        cat = Category(name=name, slug=slug, default_price=default_price, sort_order=sort_order, description=description)
        s.add(cat)
        await s.commit()
        await s.refresh(cat)
        return cat

async def update_category_infographic(slug: str, file_id: str) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(update(Category).where(Category.slug == slug).values(infographic_file_id=file_id))
        await s.commit()

async def update_category_price(slug: str, price: float) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(update(Category).where(Category.slug == slug).values(default_price=price))
        await s.commit()

async def get_category_items(category_slug: str, active_only: bool = True, kind: str | None = None) -> list[CatalogItem]:
    async with AsyncSessionLocal() as s:
        cat_result = await s.execute(select(Category).where(Category.slug == category_slug))
        cat = cat_result.scalar_one_or_none()
        if not cat:
            return []
        q = select(CatalogItem).where(CatalogItem.category_id == cat.id).order_by(CatalogItem.photo_number)
        if active_only:
            q = q.where(CatalogItem.is_active.is_(True))
        if kind:
            q = q.where(CatalogItem.kind == kind)
        result = await s.execute(q)
        return list(result.scalars().all())

async def get_item_by_id(item_id: int) -> Optional[CatalogItem]:
    async with AsyncSessionLocal() as s:
        return await s.get(CatalogItem, item_id)

async def create_catalog_item(category_slug: str, photo_number: int, price: float, stock: int, file_id: str | None = None) -> CatalogItem:
    async with AsyncSessionLocal() as s:
        cat_result = await s.execute(select(Category).where(Category.slug == category_slug))
        cat = cat_result.scalar_one_or_none()
        item = CatalogItem(category_id=cat.id, photo_number=photo_number, price=price, stock=stock, file_id=file_id)
        s.add(item)
        await s.commit()
        await s.refresh(item)
        return item

async def update_item_stock(item_id: int, delta: int) -> None:
    async with AsyncSessionLocal() as s:
        item = await s.get(CatalogItem, item_id)
        if item:
            item.stock = max(0, item.stock + delta)
            await s.commit()

async def check_order_stock(order_id: int) -> list[str]:
    """Проверяет, что по всем позициям заказа хватает остатка.
    Возвращает список проблем (пустой — всё в порядке)."""
    problems: list[str] = []
    async with AsyncSessionLocal() as s:
        order = await s.get(Order, order_id)
        if not order:
            return ["Заказ не найден"]
        for oi in order.items:
            item = await s.get(CatalogItem, oi.catalog_item_id)
            if not item or not item.is_active:
                problems.append(f"фото №{oi.catalog_item_id} — позиция снята с продажи")
            elif item.stock < oi.quantity:
                problems.append(f"фото №{item.photo_number} — доступно только {item.stock} шт. (в заказе {oi.quantity})")
    return problems

async def reserve_stock_for_order(order_id: int) -> None:
    """Списывает остатки по позициям заказа (при подтверждении заказа)."""
    async with AsyncSessionLocal() as s:
        order = await s.get(Order, order_id)
        if not order:
            return
        for oi in order.items:
            item = await s.get(CatalogItem, oi.catalog_item_id)
            if item:
                item.stock = max(0, item.stock - oi.quantity)
        await s.commit()

async def restore_stock_for_order(order_id: int) -> None:
    """Возвращает остатки по позициям заказа (при отмене заказа)."""
    async with AsyncSessionLocal() as s:
        order = await s.get(Order, order_id)
        if not order:
            return
        for oi in order.items:
            item = await s.get(CatalogItem, oi.catalog_item_id)
            if item:
                item.stock += oi.quantity
        await s.commit()

async def set_item_stock(item_id: int, stock: int) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(update(CatalogItem).where(CatalogItem.id == item_id).values(stock=stock))
        await s.commit()

async def set_item_price(item_id: int, price: float) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(update(CatalogItem).where(CatalogItem.id == item_id).values(price=price))
        await s.commit()

async def toggle_item_active(item_id: int) -> bool:
    async with AsyncSessionLocal() as s:
        item = await s.get(CatalogItem, item_id)
        if item:
            item.is_active = not item.is_active
            await s.commit()
            return item.is_active
        return False

async def delete_catalog_item(item_id: int) -> None:
    async with AsyncSessionLocal() as s:
        item = await s.get(CatalogItem, item_id)
        if item:
            await s.delete(item)
            await s.commit()


async def get_draft_order(telegram_id: int) -> Optional[Order]:
    async with AsyncSessionLocal() as s:
        user_result = await s.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return None
        result = await s.execute(select(Order).where(Order.user_id == user.id, Order.status == OrderStatus.DRAFT).order_by(Order.created_at.desc()))
        return result.scalars().first()

# Статусы, в которых заказ «в работе» у клиента (не черновик, не финал)
ACTIVE_ORDER_STATUSES = (
    OrderStatus.AWAITING_PREPAYMENT,
    OrderStatus.RECEIPT_RECEIVED,
    OrderStatus.ON_REVIEW,
    OrderStatus.PAYMENT_CONFIRMED,
    OrderStatus.ORDER_CONFIRMED,
    OrderStatus.PREPARING,
    OrderStatus.SHIPPED,
)

# Статусы, в которых клиент может (повторно) отправить чек
RECEIPT_ALLOWED_STATUSES = (
    OrderStatus.AWAITING_PREPAYMENT,
    OrderStatus.RECEIPT_RECEIVED,
)

async def get_active_order(telegram_id: int) -> Optional[Order]:
    """Последний заказ пользователя в работе (не черновик и не завершён/отменён)."""
    async with AsyncSessionLocal() as s:
        user_result = await s.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return None
        result = await s.execute(
            select(Order)
            .where(Order.user_id == user.id, Order.status.in_(ACTIVE_ORDER_STATUSES))
            .order_by(Order.created_at.desc())
        )
        return result.scalars().first()

async def get_or_create_draft(telegram_id: int, username: str | None) -> Order:
    user = await get_or_create_user(telegram_id, username)
    draft = await get_draft_order(telegram_id)
    if draft:
        return draft
    async with AsyncSessionLocal() as s:
        delivery_cost_str = await get_setting("delivery_cost")
        delivery_cost = float(delivery_cost_str) if delivery_cost_str else 300.0
        order = Order(user_id=user.id, delivery_cost=delivery_cost, pay_token=secrets.token_urlsafe(16))
        s.add(order)
        await s.commit()
        await s.refresh(order)
        return order

async def add_item_to_cart(order_id: int, catalog_item_id: int, quantity: int) -> int:
    """Добавляет позицию в корзину с учётом остатка и уже лежащего в корзине.

    Возвращает фактически добавленное количество (0 — свободного остатка нет).
    """
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(OrderItem).where(OrderItem.order_id == order_id, OrderItem.catalog_item_id == catalog_item_id))
        existing = result.scalar_one_or_none()
        item = await s.get(CatalogItem, catalog_item_id)
        in_cart = existing.quantity if existing else 0
        can_add = max(0, item.stock - in_cart)
        to_add = min(quantity, can_add)
        if to_add <= 0:
            return 0
        if existing:
            existing.quantity += to_add
        else:
            s.add(OrderItem(order_id=order_id, catalog_item_id=catalog_item_id, quantity=to_add, price_at_order=item.price))
        await s.commit()
        await _recalculate_order(order_id, s)
        return to_add

async def remove_item_from_cart(order_item_id: int) -> None:
    async with AsyncSessionLocal() as s:
        oi = await s.get(OrderItem, order_item_id)
        if oi:
            order_id = oi.order_id
            await s.delete(oi)
            await s.commit()
            await _recalculate_order(order_id, s)

async def update_item_quantity(order_item_id: int, quantity: int) -> None:
    async with AsyncSessionLocal() as s:
        oi = await s.get(OrderItem, order_item_id)
        if oi:
            if quantity <= 0:
                order_id = oi.order_id
                await s.delete(oi)
                await s.commit()
                await _recalculate_order(order_id, s)
            else:
                oi.quantity = quantity
                await s.commit()
                await _recalculate_order(oi.order_id, s)

async def clear_cart(order_id: int) -> None:
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(OrderItem).where(OrderItem.order_id == order_id))
        for oi in result.scalars().all():
            await s.delete(oi)
        await s.commit()
        await _recalculate_order(order_id, s)

async def _recalculate_order(order_id: int, s: AsyncSession) -> None:
    order = await s.get(Order, order_id)
    if not order:
        return
    result = await s.execute(select(OrderItem).where(OrderItem.order_id == order_id))
    items = result.scalars().all()
    plants_cost = sum(oi.quantity * oi.price_at_order for oi in items)
    total = plants_cost + order.delivery_cost
    prepayment = round(total * 0.30, 2)
    order.plants_cost = plants_cost
    order.total_cost = total
    order.prepayment = prepayment
    order.remainder = round(total - prepayment, 2)
    await s.commit()

async def get_order_by_id(order_id: int) -> Optional[Order]:
    async with AsyncSessionLocal() as s:
        return await s.get(Order, order_id)

async def get_orders_list(status: OrderStatus | None = None, limit: int = 50) -> list[Order]:
    async with AsyncSessionLocal() as s:
        q = select(Order).order_by(Order.created_at.desc()).limit(limit)
        if status:
            q = q.where(Order.status == status)
        result = await s.execute(q)
        return list(result.scalars().all())

async def get_user_orders(telegram_id: int, limit: int = 5) -> list[Order]:
    """Последние заказы пользователя (все статусы, новые сверху)."""
    async with AsyncSessionLocal() as s:
        user_result = await s.execute(select(User).where(User.telegram_id == telegram_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return []
        result = await s.execute(
            select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

async def save_user_contact_data(telegram_id: int, full_name: str, phone: str, city: str, pickup_point: str) -> None:
    """Сохраняет данные клиента в профиль (для сценария «как в прошлый раз»)."""
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user:
            user.full_name = full_name
            user.phone = phone
            user.city = city
            user.pickup_point = pickup_point
            await s.commit()

async def get_user_by_telegram_id(telegram_id: int) -> Optional[User]:
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

async def update_order_status(order_id: int, status: OrderStatus) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(update(Order).where(Order.id == order_id).values(status=status))
        await s.commit()

async def save_customer_data(order_id: int, full_name: str, phone: str, city: str, pickup_point: str, comment: str | None) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(update(Order).where(Order.id == order_id).values(full_name=full_name, phone=phone, city=city, pickup_point=pickup_point, comment=comment))
        await s.commit()

async def save_receipt(order_id: int, file_id: str) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(update(Order).where(Order.id == order_id).values(receipt_file_id=file_id, status=OrderStatus.ON_REVIEW))
        await s.commit()

async def save_track_number(order_id: int, track: str) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(update(Order).where(Order.id == order_id).values(track_number=track, status=OrderStatus.SHIPPED))
        await s.commit()

async def set_admin_comment(order_id: int, comment: str) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(update(Order).where(Order.id == order_id).values(admin_comment=comment))
        await s.commit()

async def log_event(event: str, user_telegram_id: int | None = None, order_id: int | None = None, details: str | None = None) -> None:
    async with AsyncSessionLocal() as s:
        s.add(EventLog(event=event, user_telegram_id=user_telegram_id, order_id=order_id, details=details))
        await s.commit()


# ---------- Сотрудники и реферальный учёт ----------

async def get_or_create_employee(name: str, telegram_id: int | None = None, ref_code: str | None = None) -> Employee:
    """Создаёт сотрудника (или возвращает по ref_code/telegram_id). ref_code по умолчанию — из имени."""
    async with AsyncSessionLocal() as s:
        if ref_code:
            result = await s.execute(select(Employee).where(Employee.ref_code == ref_code))
            existing = result.scalar_one_or_none()
            if existing:
                return existing
        if telegram_id:
            result = await s.execute(select(Employee).where(Employee.telegram_id == telegram_id))
            existing = result.scalar_one_or_none()
            if existing:
                return existing
        if not ref_code:
            base = _slugify_name(name) or f"emp{int(datetime.utcnow().timestamp())}"
            ref_code = base
            n = 2
            while (await s.execute(select(Employee).where(Employee.ref_code == ref_code))).scalar_one_or_none():
                ref_code = f"{base}{n}"
                n += 1
        emp = Employee(name=name, telegram_id=telegram_id, ref_code=ref_code)
        s.add(emp)
        await s.commit()
        await s.refresh(emp)
        return emp


def _slugify_name(name: str) -> str:
    import re
    mapping = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
        "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
        "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
        "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    slug = "".join(mapping.get(ch, ch) for ch in name.lower())
    return re.sub(r"[^a-z0-9]", "", slug)


async def get_employee_by_ref_code(ref_code: str) -> Optional[Employee]:
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(Employee).where(Employee.ref_code == ref_code, Employee.is_active.is_(True)))
        return result.scalar_one_or_none()


async def get_employee_by_telegram_id(telegram_id: int) -> Optional[Employee]:
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(Employee).where(Employee.telegram_id == telegram_id, Employee.is_active.is_(True)))
        return result.scalar_one_or_none()


async def list_employees() -> list[Employee]:
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(Employee).order_by(Employee.created_at))
        return list(result.scalars().all())


async def assign_employee_to_user(user_id: int, employee_id: int) -> None:
    """Привязывает клиента к сотруднику, если ещё не привязан (первый источник побеждает)."""
    async with AsyncSessionLocal() as s:
        user = await s.get(User, user_id)
        if user and user.employee_id is None:
            user.employee_id = employee_id
            await s.commit()


async def get_employee_stats(employee_id: int) -> dict:
    """Статистика сотрудника: клиенты, их заказы (без черновиков), суммы."""
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(User).where(User.employee_id == employee_id).order_by(User.created_at.desc()))
        clients = list(result.scalars().all())
        client_ids = [u.id for u in clients]
        orders: list[Order] = []
        if client_ids:
            result = await s.execute(
                select(Order)
                .where(Order.user_id.in_(client_ids), Order.status != OrderStatus.DRAFT)
                .order_by(Order.created_at.desc())
            )
            orders = list(result.scalars().all())
        total = sum(o.total_cost for o in orders)
        return {"clients": clients, "orders": orders, "total": total}


# ---------- Сессии сотрудников (вход на сайт) ----------

async def create_employee_session(employee_id: int, token: str, expires_at: datetime, user_agent: str | None = None, ip: str | None = None) -> EmployeeSession:
    async with AsyncSessionLocal() as s:
        session = EmployeeSession(
            employee_id=employee_id,
            token=token,
            expires_at=expires_at,
            user_agent=user_agent,
            ip=ip,
        )
        s.add(session)
        await s.commit()
        await s.refresh(session)
        return session


async def get_employee_session(token: str) -> Optional[EmployeeSession]:
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(EmployeeSession).where(EmployeeSession.token == token))
        return result.scalar_one_or_none()


async def delete_employee_session(token: str) -> None:
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(EmployeeSession).where(EmployeeSession.token == token))
        session = result.scalar_one_or_none()
        if session:
            await s.delete(session)
            await s.commit()


async def delete_expired_sessions() -> None:
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(EmployeeSession).where(EmployeeSession.expires_at < datetime.utcnow()))
        for session in result.scalars().all():
            await s.delete(session)
        await s.commit()


# ---------- Реферальные события ----------

async def log_referral_event(employee_id: int, source: str, user_id: int | None = None, user_agent: str | None = None, ip: str | None = None) -> None:
    async with AsyncSessionLocal() as s:
        event = ReferralEvent(
            employee_id=employee_id,
            source=source,
            user_id=user_id,
            user_agent=user_agent,
            ip=ip,
        )
        s.add(event)
        await s.commit()


async def get_referral_events(employee_id: int, limit: int = 100) -> list[ReferralEvent]:
    async with AsyncSessionLocal() as s:
        result = await s.execute(
            select(ReferralEvent)
            .where(ReferralEvent.employee_id == employee_id)
            .order_by(ReferralEvent.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def get_referral_stats(employee_id: int) -> dict:
    """Сводка по переходам: количество визитов по источникам."""
    async with AsyncSessionLocal() as s:
        result = await s.execute(
            select(ReferralEvent.source, func.count())
            .where(ReferralEvent.employee_id == employee_id)
            .group_by(ReferralEvent.source)
        )
        by_source = {row[0]: row[1] for row in result.all()}
        total = sum(by_source.values())
        return {"total": total, "by_source": by_source}


# ---------- Управление сотрудниками ----------

async def get_employee_by_username(username: str) -> Optional[Employee]:
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(Employee).where(Employee.username == username))
        return result.scalar_one_or_none()


async def get_employee_by_secret_token(secret_token: str) -> Optional[Employee]:
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(Employee).where(Employee.secret_token == secret_token, Employee.is_active.is_(True)))
        return result.scalar_one_or_none()


async def get_employee_by_id(employee_id: int) -> Optional[Employee]:
    async with AsyncSessionLocal() as s:
        return await s.get(Employee, employee_id)


async def update_employee_password(employee_id: int, password_hash: str) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(update(Employee).where(Employee.id == employee_id).values(password_hash=password_hash))
        await s.commit()


async def update_employee_secret_token(employee_id: int, secret_token: str) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(update(Employee).where(Employee.id == employee_id).values(secret_token=secret_token))
        await s.commit()


async def update_employee_telegram_id(employee_id: int, telegram_id: int) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(update(Employee).where(Employee.id == employee_id).values(telegram_id=telegram_id))
        await s.commit()


async def update_employee_telegram_username(employee_id: int, telegram_username: str | None) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(
            update(Employee).where(Employee.id == employee_id).values(telegram_username=_clean_tg_username(telegram_username))
        )
        await s.commit()


async def update_employee_last_login(employee_id: int) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(update(Employee).where(Employee.id == employee_id).values(last_login_at=datetime.utcnow()))
        await s.commit()


async def toggle_employee_active(employee_id: int) -> bool:
    async with AsyncSessionLocal() as s:
        emp = await s.get(Employee, employee_id)
        if emp:
            emp.is_active = not emp.is_active
            await s.commit()
            return emp.is_active
        return False


async def set_employee_role(employee_id: int, role: str) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(update(Employee).where(Employee.id == employee_id).values(role=role))
        await s.commit()


async def create_employee_with_auth(
    name: str,
    username: str,
    password_hash: str,
    telegram_id: int | None = None,
    telegram_username: str | None = None,
    role: str = "manager",
    secret_token: str | None = None,
) -> Employee:
    """Создаёт сотрудника с логином/паролем."""
    async with AsyncSessionLocal() as s:
        # Уникальный ref_code из имени
        base = _slugify_name(name) or f"emp{int(datetime.utcnow().timestamp())}"
        ref_code = base
        n = 2
        while (await s.execute(select(Employee).where(Employee.ref_code == ref_code))).scalar_one_or_none():
            ref_code = f"{base}{n}"
            n += 1
        emp = Employee(
            name=name,
            username=username,
            telegram_username=_clean_tg_username(telegram_username),
            password_hash=password_hash,
            telegram_id=telegram_id,
            ref_code=ref_code,
            role=role,
            secret_token=secret_token,
        )
        s.add(emp)
        await s.commit()
        await s.refresh(emp)
        return emp


def _clean_tg_username(value: str | None) -> str | None:
    """Приводит Telegram-username к виду без @."""
    if not value:
        return None
    v = value.strip().lstrip("@")
    return v if v else None


async def get_manager_contact_for_user(user: User | None) -> str:
    """Возвращает контакт менеджера для клиента: @telegram_username реферального менеджера или глобальный контакт."""
    if user and user.employee_id:
        emp = await get_employee_by_id(user.employee_id)
        if emp and emp.telegram_username:
            return "@" + emp.telegram_username
    return (await get_setting("manager_contact")) or ""


# ---------- Веб-заказы (Mini App / сайт) ----------

async def get_or_create_site_user(phone: str, full_name: str | None = None, source: str = "site") -> User:
    """Клиент без Telegram: ищем по телефону, иначе создаём."""
    phone_norm = phone.strip()
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(User).where(User.phone == phone_norm).order_by(User.created_at.desc()))
        user = result.scalars().first()
        if not user:
            user = User(telegram_id=None, phone=phone_norm, full_name=full_name, source=source)
            s.add(user)
        if not user.site_token:
            user.site_token = secrets.token_urlsafe(16)
        await s.commit()
        await s.refresh(user)
        return user


async def get_user_by_site_token(site_token: str) -> Optional[User]:
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(User).where(User.site_token == site_token))
        return result.scalar_one_or_none()


async def get_user_by_id(user_id: int) -> Optional[User]:
    async with AsyncSessionLocal() as s:
        return await s.get(User, user_id)


async def get_orders_by_user(user_id: int) -> list[Order]:
    async with AsyncSessionLocal() as s:
        result = await s.execute(
            select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
        )
        return list(result.scalars().all())


# ---------- Чат клиент ↔ менеджер (сайт + бот, единая история) ----------

async def add_chat_message(
    user_id: int,
    sender: str,  # client | manager
    text: str,
    via: str,  # site | bot
    order_id: int | None = None,
) -> ChatMessage:
    async with AsyncSessionLocal() as s:
        msg = ChatMessage(
            user_id=user_id, sender=sender, text=text.strip(), via=via, order_id=order_id,
            read_by_manager=(sender == "manager"),
            read_by_client=(sender == "client"),
        )
        s.add(msg)
        await s.commit()
        await s.refresh(msg)
        return msg


async def get_chat_history(user_id: int, after_id: int = 0, limit: int = 100) -> list[ChatMessage]:
    async with AsyncSessionLocal() as s:
        result = await s.execute(
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id, ChatMessage.id > after_id)
            .order_by(ChatMessage.id.asc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def mark_chat_read_by_client(user_id: int) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(
            update(ChatMessage)
            .where(ChatMessage.user_id == user_id, ChatMessage.sender == "manager")
            .values(read_by_client=True)
        )
        await s.commit()


async def mark_chat_read_by_manager(user_id: int) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(
            update(ChatMessage)
            .where(ChatMessage.user_id == user_id, ChatMessage.sender == "client")
            .values(read_by_manager=True)
        )
        await s.commit()


async def get_unread_chat_user_ids() -> list[int]:
    """user_id с непрочитанными сообщениями от клиентов (для уведомления менеджеров)."""
    async with AsyncSessionLocal() as s:
        result = await s.execute(
            select(ChatMessage.user_id)
            .where(ChatMessage.sender == "client", ChatMessage.read_by_manager.is_(False))
            .distinct()
        )
        return [r[0] for r in result.all()]


async def create_web_order(
    user_id: int,
    items: list[dict],  # [{"item_id": int, "quantity": int}]
    full_name: str,
    phone: str,
    city: str,
    pickup_point: str,
    comment: str | None,
    source: str,
    employee_id: int | None = None,
) -> tuple[Order | None, list[str]]:
    """Создаёт заказ из Mini App / сайта. Возвращает (заказ, список проблем с остатками)."""
    async with AsyncSessionLocal() as s:
        user = await s.get(User, user_id)
        if not user:
            return None, ["Пользователь не найден"]
        problems: list[str] = []
        resolved: list[tuple[CatalogItem, int]] = []
        for it in items:
            item = await s.get(CatalogItem, it["item_id"])
            qty = max(1, int(it["quantity"]))
            if not item or not item.is_active:
                problems.append(f"Позиция #{it['item_id']} снята с продажи")
            elif item.stock < qty:
                problems.append(f"«{item.title or 'фото №' + str(item.photo_number)}» — доступно только {item.stock} шт.")
            else:
                resolved.append((item, qty))
        if problems:
            return None, problems
        if not resolved:
            return None, ["Корзина пуста"]
        delivery_str = await get_setting("delivery_cost")
        delivery_cost = float(delivery_str) if delivery_str else 300.0
        order = Order(
            user_id=user.id,
            status=OrderStatus.AWAITING_PREPAYMENT,
            full_name=full_name, phone=phone, city=city,
            pickup_point=pickup_point, comment=comment,
            delivery_cost=delivery_cost,
            employee_id=employee_id if employee_id is not None else user.employee_id,
            source=source,
            pay_token=secrets.token_urlsafe(16),
        )
        s.add(order)
        await s.flush()
        for item, qty in resolved:
            s.add(OrderItem(order_id=order.id, catalog_item_id=item.id, quantity=qty, price_at_order=item.price))
            item.stock = max(0, item.stock - qty)
        await s.commit()
        await _recalculate_order(order.id, s)
        await s.refresh(order)
        # Данные клиента — в профиль (для «как в прошлый раз»)
        user.full_name, user.phone, user.city, user.pickup_point = full_name, phone, city, pickup_point
        await s.commit()
        return order, []


# ---------- Платежи и автопроверка чеков ----------

async def ensure_pay_token(order_id: int) -> str | None:
    """Гарантирует наличие pay_token у заказа (для старых заказов без токена)."""
    async with AsyncSessionLocal() as s:
        order = await s.get(Order, order_id)
        if not order:
            return None
        if not order.pay_token:
            order.pay_token = secrets.token_urlsafe(16)
            await s.commit()
        return order.pay_token


async def get_order_by_pay_token(pay_token: str) -> Optional[Order]:
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(Order).where(Order.pay_token == pay_token))
        return result.scalar_one_or_none()


async def create_payment(
    order_id: int,
    amount: float,
    kind: str = "prepayment",
    receipt_file_id: str | None = None,
    receipt_hash: str | None = None,
    operation_id: str | None = None,
    check_status: str = "needs_review",
    check_details: str | None = None,
    paid_at: datetime | None = None,
) -> Payment:
    async with AsyncSessionLocal() as s:
        payment = Payment(
            order_id=order_id,
            amount=amount,
            kind=kind,
            receipt_file_id=receipt_file_id,
            receipt_hash=receipt_hash,
            operation_id=operation_id,
            check_status=check_status,
            check_details=check_details,
            paid_at=paid_at,
        )
        s.add(payment)
        await s.commit()
        await s.refresh(payment)
        return payment


async def get_pending_payments() -> list[Payment]:
    """Платежи, ожидающие ручной проверки админом."""
    async with AsyncSessionLocal() as s:
        result = await s.execute(
            select(Payment)
            .where(Payment.check_status == "needs_review", Payment.verified.is_(None))
            .order_by(Payment.created_at.desc())
        )
        return list(result.scalars().all())


async def get_latest_payment(order_id: int, kind: str | None = None) -> Optional[Payment]:
    """Последний платёж по заказу (опционально — по виду: prepayment/remainder)."""
    async with AsyncSessionLocal() as s:
        q = select(Payment).where(Payment.order_id == order_id).order_by(Payment.created_at.desc())
        if kind:
            q = q.where(Payment.kind == kind)
        result = await s.execute(q)
        return result.scalars().first()


async def is_receipt_seen(receipt_hash: str | None, operation_id: str | None) -> Optional[Payment]:
    """Анти-повтор: ищет уже подтверждённый платёж с таким же файлом или номером операции."""
    async with AsyncSessionLocal() as s:
        confirmed = (Payment.verified.is_(True)) | (Payment.check_status == "auto_approved")
        if receipt_hash:
            result = await s.execute(select(Payment).where(Payment.receipt_hash == receipt_hash, confirmed))
            found = result.scalars().first()
            if found:
                return found
        if operation_id:
            result = await s.execute(select(Payment).where(Payment.operation_id == operation_id, confirmed))
            found = result.scalars().first()
            if found:
                return found
        return None


async def mark_payment_result(payment_id: int, check_status: str, verified: bool | None = None) -> None:
    async with AsyncSessionLocal() as s:
        payment = await s.get(Payment, payment_id)
        if payment:
            payment.check_status = check_status
            if verified is not None:
                payment.verified = verified
            await s.commit()


async def set_order_paid(order_id: int, kind: str, paid_at: datetime | None = None) -> None:
    """Проставляет время оплаты предоплаты/остатка в заказе."""
    field = "prepayment_paid_at" if kind == "prepayment" else "remainder_paid_at"
    async with AsyncSessionLocal() as s:
        await s.execute(update(Order).where(Order.id == order_id).values(**{field: paid_at or datetime.utcnow()}))
        await s.commit()


async def approve_payment_for_order(order_id: int, kind: str | None = None) -> Optional[Payment]:
    """Ручное подтверждение админом: помечает последний платёж заказа как проверенный."""
    payment = await get_latest_payment(order_id, kind)
    if payment and payment.check_status == "needs_review":
        # check_status оставляем needs_review (решение принял человек), verified=True — маркер подтверждения
        await mark_payment_result(payment.id, "needs_review", verified=True)
        await set_order_paid(order_id, payment.kind, payment.paid_at)
        # перечитываем, чтобы вернуть свежий объект (verified=True), а не устаревший из кеша сессии
        return await get_latest_payment(order_id, kind)
    return None


async def reject_payment_for_order(order_id: int, kind: str | None = None) -> Optional[Payment]:
    """Ручное отклонение админом: помечает последний платёж заказа как отклонённый."""
    payment = await get_latest_payment(order_id, kind)
    if payment and payment.check_status == "needs_review":
        await mark_payment_result(payment.id, "rejected", verified=False)
        return payment
    return None


# ---------- Реквизиты оплаты ----------

async def get_payment_requisites() -> dict:
    """Структурированные реквизиты из настроек + fallback-текст (старые реквизиты)."""
    from config import DEFAULT_PAYMENT_REQUISITES
    return {
        "card": (await get_setting("payment_card") or "").strip(),
        "phone_sbp": (await get_setting("payment_phone_sbp") or "").strip(),
        "wallet": (await get_setting("payment_wallet") or "").strip(),
        "recipient_name": (await get_setting("payment_recipient_name") or "").strip(),
        "fallback_text": (await get_setting("payment_requisites") or DEFAULT_PAYMENT_REQUISITES).strip(),
    }


def format_requisites_text(requisites: dict) -> str:
    """Собирает непустые поля реквизитов в читабельный блок для клиента.

    Если все структурированные поля пустые — возвращает fallback-текст.
    """
    lines = []
    if requisites.get("card"):
        lines.append(f"Карта: {requisites['card']}")
    if requisites.get("phone_sbp"):
        lines.append(f"СБП (телефон): {requisites['phone_sbp']}")
    if requisites.get("wallet"):
        lines.append(f"Кошелёк: {requisites['wallet']}")
    if requisites.get("recipient_name"):
        lines.append(f"Получатель: {requisites['recipient_name']}")
    if not lines:
        return requisites.get("fallback_text") or ""
    return "\n".join(lines)
