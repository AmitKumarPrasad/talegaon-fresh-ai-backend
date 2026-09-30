from collections.abc import Callable

from app.db import SessionLocal
from app.models import OrderItemModel, OrderModel, OrderStatusHistoryModel, ProductModel

ORDER_STATUSES = {
    "PENDING", "ADDRESS_CONFIRMED", "PAYMENT_PENDING", "CONFIRMED",
    "PACKING", "OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED",
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


def transition_order(order_id: int, new_status: str, updater: Callable | None = None) -> bool:
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
        if new_status == "CANCELLED" and order.stock_reserved:
            items = db.query(OrderItemModel).filter(OrderItemModel.order_id == order.id).all()
            for item in items:
                updated = (db.query(ProductModel).filter(ProductModel.name == item.product_name).update(
                    {ProductModel.stock_quantity: ProductModel.stock_quantity + int(item.quantity)},
                    synchronize_session=False,
                ))
                if updated != 1:
                    db.rollback()
                    return False
                product = db.query(ProductModel).filter(ProductModel.name == item.product_name).first()
                if product:
                    product.in_stock = product.stock_quantity > 0
            order.stock_reserved = False
        previous_status = order.status
        if updater is not None:
            updater(order)
        order.status = new_status
        db.add(OrderStatusHistoryModel(
            order_id=order.id, from_status=previous_status, to_status=new_status
        ))
        db.commit()
        return True
    finally:
        db.close()


def get_allowed_transitions(status: str) -> set[str]:
    return set(ALLOWED_TRANSITIONS.get(status.upper(), set()))


def list_status_history(order_id: int, customer_id: str | None = None) -> list[dict]:
    db = SessionLocal()
    try:
        query = db.query(OrderStatusHistoryModel).filter(OrderStatusHistoryModel.order_id == order_id)
        if customer_id is not None:
            query = query.join(OrderModel, OrderModel.id == OrderStatusHistoryModel.order_id).filter(OrderModel.customer_id == customer_id)
        rows = query.order_by(OrderStatusHistoryModel.id.asc()).all()
        return [{
            "id": row.id,
            "from_status": row.from_status,
            "to_status": row.to_status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        } for row in rows]
    finally:
        db.close()
