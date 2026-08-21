"""Расчёт стоимости заказа."""
from dataclasses import dataclass

@dataclass
class OrderCalc:
    plants_cost: float
    delivery_cost: float
    total: float
    prepayment: float
    remainder: float

def calculate_order(plants_cost: float, delivery_cost: float, prepayment_percent: int = 30) -> OrderCalc:
    total = plants_cost + delivery_cost
    prepayment = round(total * prepayment_percent / 100, 2)
    remainder = round(total - prepayment, 2)
    return OrderCalc(plants_cost=plants_cost, delivery_cost=delivery_cost, total=total, prepayment=prepayment, remainder=remainder)

def format_order_summary(calc: OrderCalc) -> str:
    return f"💰 Стоимость растений: *{calc.plants_cost:.0f} ₽*\n🚚 Доставка: *{calc.delivery_cost:.0f} ₽*\n────────────\n📦 Итого: *{calc.total:.0f} ₽*\n💳 Предоплата 30%: *{calc.prepayment:.0f} ₽*\n🔄 Остаток: *{calc.remainder:.0f} ₽*"
