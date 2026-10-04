from app.db import SessionLocal
from app.models import OrderItemModel, OrderModel
from app.order_status import get_allowed_transitions


def _serialize_item(item: OrderItemModel) -> dict:
    return {
        "product": item.product_name,
        "quantity": item.quantity,
        "unit_price": item.unit_price,
        "line_total": item.line_total,
    }


def _serialize_order(order: OrderModel, items: list[OrderItemModel]) -> dict:
    return {
        "order_id": order.id,
        "customer_id": order.customer_id,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "status": order.status,
        "allowed_next_statuses": sorted(get_allowed_transitions(order.status)),
        "total": order.total,
        "address": order.address,
        "payment_method": order.payment_method,
        "payment_link_url": order.payment_link_url,
        "payment_verified_at": (
            order.payment_verified_at.isoformat()
            if order.payment_verified_at
            else None
        ),
        "items": [_serialize_item(item) for item in items],
    }


def list_orders(status: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
    status = status.upper() if status else None
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)

    db = SessionLocal()
    try:
        query = db.query(OrderModel)
        if status:
            query = query.filter(OrderModel.status == status)
        orders = query.order_by(OrderModel.id.desc()).offset(offset).limit(limit).all()

        if not orders:
            return []

        order_ids = [order.id for order in orders]
        items = (
            db.query(OrderItemModel)
            .filter(OrderItemModel.order_id.in_(order_ids))
            .order_by(OrderItemModel.id.asc())
            .all()
        )
        items_by_order: dict[int, list[OrderItemModel]] = {}
        for item in items:
            items_by_order.setdefault(item.order_id, []).append(item)

        return [
            _serialize_order(order, items_by_order.get(order.id, []))
            for order in orders
        ]
    finally:
        db.close()


def get_admin_order(order_id: int) -> dict | None:
    db = SessionLocal()
    try:
        order = db.get(OrderModel, order_id)
        if not order:
            return None
        items = (
            db.query(OrderItemModel)
            .filter(OrderItemModel.order_id == order_id)
            .order_by(OrderItemModel.id.asc())
            .all()
        )
        return _serialize_order(order, items)
    finally:
        db.close()
