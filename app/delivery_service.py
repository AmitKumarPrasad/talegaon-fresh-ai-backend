import secrets
from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import OrderItemModel, OrderMessageModel, OrderModel

DELIVERY_TOKEN_TTL = timedelta(hours=24)


def _token_is_active(order: OrderModel, now: datetime | None = None) -> bool:
    # The shared delivery link is a short-lived capability. A terminal order
    # must revoke it immediately, even if its stored expiry is still in future.
    terminal_statuses = {"CANCELLED", "DELIVERED"}
    if str(getattr(order, "status", "")).upper() in terminal_statuses:
        return False
    if str(getattr(order, "delivery_status", "")).upper() in terminal_statuses:
        return False
    expires_at = order.delivery_token_expires_at
    if not expires_at:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > (now or datetime.now(timezone.utc))


def _order_dict(order: OrderModel) -> dict:
    return {
        "order_id": order.id,
        "status": order.status,
        "delivery_status": getattr(order, "delivery_status", None),
        "address": order.address,
        "delivery_person_name": order.delivery_person_name,
        "delivery_lat": order.delivery_lat,
        "delivery_lng": order.delivery_lng,
        "delivery_location_updated_at": (
            order.delivery_location_updated_at.isoformat() if order.delivery_location_updated_at else None
        ),
    }


def assign_delivery_person(order_id: int, name: str, phone: str) -> dict | None:
    db = SessionLocal()
    try:
        order = db.get(OrderModel, order_id)
        if not order:
            return None
        reassigned = order.delivery_person_phone != phone
        order.delivery_person_name = name
        order.delivery_person_phone = phone
        order.delivery_status = "ASSIGNED"
        if reassigned or not order.delivery_token or not _token_is_active(order):
            # Never leave a previously issued capability link usable for a
            # newly assigned partner.
            order.delivery_token = secrets.token_urlsafe(24)
            order.delivery_token_expires_at = datetime.now(timezone.utc) + DELIVERY_TOKEN_TTL
        db.commit()
        db.refresh(order)
        return {**_order_dict(order), "delivery_token": order.delivery_token}
    finally:
        db.close()


def get_tracking_info(order_id: int, customer_id: str) -> dict | None:
    db = SessionLocal()
    try:
        order = db.get(OrderModel, order_id)
        if not order or order.customer_id != customer_id:
            return None
        return _order_dict(order)
    finally:
        db.close()


def get_order_by_delivery_token(token: str) -> OrderModel | None:
    db = SessionLocal()
    try:
        order = db.query(OrderModel).filter(OrderModel.delivery_token == token).first()
        return order if order and _token_is_active(order) else None
    finally:
        db.close()


def get_delivery_order_summary(token: str) -> dict | None:
    db = SessionLocal()
    try:
        order = db.query(OrderModel).filter(OrderModel.delivery_token == token).first()
        if not order or not _token_is_active(order):
            return None
        items = db.query(OrderItemModel).filter(OrderItemModel.order_id == order.id).all()
        return {
            "order_id": order.id,
            "status": order.status,
            "address": order.address,
            "total": order.total,
            "payment_method": order.payment_method,
            "items": [
                {"name": item.product_name, "quantity": item.quantity}
                for item in items
            ],
        }
    finally:
        db.close()


def update_delivery_location(token: str, lat: float, lng: float) -> bool:
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        raise ValueError("Invalid coordinates.")
    db = SessionLocal()
    try:
        order = db.query(OrderModel).filter(OrderModel.delivery_token == token).first()
        if not order or not _token_is_active(order):
            return False
        order.delivery_lat = lat
        order.delivery_lng = lng
        order.delivery_location_updated_at = datetime.now(timezone.utc)
        db.commit()
        return True
    finally:
        db.close()


def _message_dict(message: OrderMessageModel) -> dict:
    return {
        "id": message.id,
        "sender": message.sender,
        "message": message.message,
        "created_at": message.created_at.isoformat(),
    }


def add_message(order_id: int, sender: str, message: str) -> dict:
    if sender not in {"customer", "delivery"}:
        raise ValueError("Invalid sender.")
    message = message.strip()
    if not message:
        raise ValueError("Message cannot be empty.")
    if len(message) > 1000:
        raise ValueError("Message is too long.")

    db = SessionLocal()
    try:
        row = OrderMessageModel(
            order_id=order_id,
            sender=sender,
            message=message,
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _message_dict(row)
    finally:
        db.close()


def list_messages(order_id: int) -> list[dict]:
    db = SessionLocal()
    try:
        rows = (
            db.query(OrderMessageModel)
            .filter(OrderMessageModel.order_id == order_id)
            .order_by(OrderMessageModel.id.asc())
            .all()
        )
        return [_message_dict(row) for row in rows]
    finally:
        db.close()


def add_message_by_customer(order_id: int, customer_id: str, message: str) -> dict | None:
    db = SessionLocal()
    try:
        order = db.get(OrderModel, order_id)
        if not order or order.customer_id != customer_id:
            return None
    finally:
        db.close()
    return add_message(order_id, "customer", message)


def add_message_by_delivery(token: str, message: str) -> dict | None:
    order = get_order_by_delivery_token(token)
    if not order:
        return None
    return add_message(order.id, "delivery", message)


def list_messages_for_customer(order_id: int, customer_id: str) -> list[dict] | None:
    db = SessionLocal()
    try:
        order = db.get(OrderModel, order_id)
        if not order or order.customer_id != customer_id:
            return None
    finally:
        db.close()
    return list_messages(order_id)


def list_messages_for_delivery(token: str) -> list[dict] | None:
    order = get_order_by_delivery_token(token)
    if not order:
        return None
    return list_messages(order.id)
