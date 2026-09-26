from app.db import SessionLocal
from app.models import OrderModel

ORDER_STATUSES = {
    "PENDING",
    "ADDRESS_CONFIRMED",
    "PAYMENT_PENDING",
    "CONFIRMED",
    "PACKING",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "CANCELLED",
}

ALLOWED_TRANSITIONS = {
    "PENDING": {"ADDRESS_CONFIRMED", "CANCELLED"},
    "ADDRESS_CONFIRMED": {"PAYMENT_PENDING", "CONFIRMED", "CANCELLED"},
    "PAYMENT_PENDING": {"CONFIRMED", "CANCELLED"},
    "CONFIRMED": {"PACKING", "CANCELLED"},
    "PACKING": {"OUT_FOR_DELIVERY"},
    "OUT_FOR_DELIVERY": {"DELIVERED"},
    "DELIVERED": set(),
    "CANCELLED": set(),
}


def transition_order(order_id: int, new_status: str) -> bool:
    new_status = new_status.upper()
    if new_status not in ORDER_STATUSES:
        return False

    db = SessionLocal()
    try:
        order = db.get(OrderModel, order_id)
        if not order or new_status == order.status:
            return False
        if new_status not in ALLOWED_TRANSITIONS.get(order.status, set()):
            return False
        order.status = new_status
        db.commit()
        return True
    finally:
        db.close()


def get_allowed_transitions(status: str) -> set[str]:
    return set(ALLOWED_TRANSITIONS.get(status.upper(), set()))
