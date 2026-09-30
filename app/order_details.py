from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import OrderModel, OrderStatusHistoryModel


def update_address(order_id: int, address: str) -> bool:
    from app.order_status import transition_order
    return transition_order(order_id, "ADDRESS_CONFIRMED", lambda order: setattr(order, "address", address.strip()))


def update_payment(order_id: int, method: str) -> bool:
    method = method.upper()
    if method not in {"UPI", "COD"}:
        return False
    from app.order_status import transition_order
    new_status = "PAYMENT_PENDING" if method == "UPI" else "CONFIRMED"
    def update(order):
        order.payment_method = method
    return transition_order(order_id, new_status, update)


def save_payment_link(order_id: int, payment_link_id: str, payment_link_url: str) -> bool:
    from app.order_status import transition_order
    def update(order):
        order.razorpay_payment_link_id = payment_link_id
        order.payment_link_url = payment_link_url
    return transition_order(order_id, "PAYMENT_PENDING", update)


def confirm_upi_payment(order_id: int, payment_link_id: str, payment_id: str, event_id: str | None, amount_paise: int) -> bool:
    db = SessionLocal()
    try:
        order = db.query(OrderModel).filter(OrderModel.id == order_id).with_for_update().first()
        if not order or order.payment_method != "UPI" or order.status != "PAYMENT_PENDING":
            return False
        expected_amount = int(round(order.total * 100))
        if amount_paise != expected_amount:
            return False
        if order.razorpay_payment_link_id and order.razorpay_payment_link_id != payment_link_id:
            return False
        previous_status = order.status
        order.razorpay_payment_link_id = payment_link_id
        order.razorpay_payment_id = payment_id
        order.razorpay_event_id = event_id
        order.payment_verified_at = datetime.now(timezone.utc)
        order.status = "CONFIRMED"
        db.add(OrderStatusHistoryModel(order_id=order.id, from_status=previous_status, to_status="CONFIRMED"))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return False
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
            "order_id": order.id, "customer_id": order.customer_id, "status": order.status,
            "total": order.total, "address": order.address, "payment_method": order.payment_method,
            "payment_link_url": order.payment_link_url,
            "razorpay_payment_link_id": order.razorpay_payment_link_id,
            "razorpay_payment_id": order.razorpay_payment_id,
            "payment_verified_at": order.payment_verified_at.isoformat() if order.payment_verified_at else None,
        }
    finally:
        db.close()


def get_customer_order(order_id: int, customer_id: str):
    order = get_order(order_id)
    if not order or order["customer_id"] != customer_id:
        return None
    return {
        "order_id": order["order_id"], "status": order["status"], "total": order["total"],
        "address": order["address"], "payment_method": order["payment_method"],
        "payment_link_url": order["payment_link_url"], "payment_verified_at": order["payment_verified_at"],
    }


def transition_order_status(order_id: int, status: str) -> bool:
    from app.order_status import transition_order
    return transition_order(order_id, status)
