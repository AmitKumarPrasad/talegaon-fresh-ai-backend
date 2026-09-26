from app.db import SessionLocal
from app.models import OrderModel


def update_address(order_id: int, address: str) -> bool:
    db = SessionLocal()
    try:
        order = db.get(OrderModel, order_id)
        if not order:
            return False
        order.address = address.strip()
        order.status = "ADDRESS_CONFIRMED"
        db.commit()
        return True
    finally:
        db.close()


def update_payment(order_id: int, method: str) -> bool:
    method = method.upper()
    if method not in {"UPI", "COD"}:
        return False
    db = SessionLocal()
    try:
        order = db.get(OrderModel, order_id)
        if not order:
            return False
        order.payment_method = method
        order.status = "PAYMENT_PENDING" if method == "UPI" else "CONFIRMED"
        db.commit()
        return True
    finally:
        db.close()


def get_order(order_id: int):
    db = SessionLocal()
    try:
        order = db.get(OrderModel, order_id)
        if not order:
            return None
        return {
            "order_id": order.id,
            "customer_id": order.customer_id,
            "status": order.status,
            "total": order.total,
            "address": order.address,
            "payment_method": order.payment_method,
        }
    finally:
        db.close()


def get_customer_order(order_id: int, customer_id: str):
    order = get_order(order_id)
    if not order or order["customer_id"] != customer_id:
        return None
    return order
