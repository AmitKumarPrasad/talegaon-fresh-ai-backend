from datetime import datetime, timezone

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


def save_payment_link(order_id: int, payment_link_id: str, payment_link_url: str) -> bool:
    db = SessionLocal()
    try:
        order = db.get(OrderModel, order_id)
        if not order:
            return False
        order.razorpay_payment_link_id = payment_link_id
        order.payment_link_url = payment_link_url
        order.status = "PAYMENT_PENDING"
        db.commit()
        return True
    finally:
        db.close()


def confirm_upi_payment(
    order_id: int,
    payment_link_id: str,
    payment_id: str,
    event_id: str | None,
    amount_paise: int,
) -> bool:
    db = SessionLocal()
    try:
        order = db.get(OrderModel, order_id)
        if not order or order.payment_method != "UPI":
            return False
        expected_amount = int(round(order.total * 100))
        if amount_paise != expected_amount:
            return False
        if order.razorpay_payment_link_id and order.razorpay_payment_link_id != payment_link_id:
            return False
        if order.razorpay_payment_id == payment_id and order.status == "CONFIRMED":
            return False
        order.razorpay_payment_link_id = payment_link_id
        order.razorpay_payment_id = payment_id
        order.razorpay_event_id = event_id
        order.payment_verified_at = datetime.now(timezone.utc)
        order.status = "CONFIRMED"
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
            "payment_link_url": order.payment_link_url,
            "razorpay_payment_id": order.razorpay_payment_id,
        }
    finally:
        db.close()


def get_customer_order(order_id: int, customer_id: str):
    order = get_order(order_id)
    if not order or order["customer_id"] != customer_id:
        return None
    return order


def transition_order_status(order_id: int, status: str) -> bool:
    from app.order_status import transition_order
    return transition_order(order_id, status)
