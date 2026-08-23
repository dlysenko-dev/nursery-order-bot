"""Расчёт стоимости заказа."""
from dataclasses import dataclass

@dataclass
class OrderCalc:
    plants_cost: float
    delivery_cost: float
    total: float
    prepayment: float
    remainder: float

def calculate_order(plants_cost: float, delivery_cost: float, prepayment_percent: int = 100) -> OrderCalc:
    total = plants_cost + delivery_cost
    prepayment = round(total * prepayment_percent / 100, 2)
    remainder = round(total - prepayment, 2)
    return OrderCalc(plants_cost=plants_cost, delivery_cost=delivery_cost, total=total, prepayment=prepayment, remainder=remainder)

def format_order_summary(calc: OrderCalc) -> str:
    lines = [
        f"💰 Стоимость растений: *{calc.plants_cost:.0f} ₽*",
        f"🚚 Доставка: *{calc.delivery_cost:.0f} ₽*",
        "────────────",
        f"📦 Итого: *{calc.total:.0f} ₽*",
        f"💳 К оплате (полная предоплата): *{calc.prepayment:.0f} ₽*",
    ]
    if calc.remainder > 0:
        lines.append(f"🔄 Остаток: *{calc.remainder:.0f} ₽*")
    return "\n".join(lines)
