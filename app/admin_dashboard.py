from datetime import datetime, timezone

from app.db import SessionLocal
from app.models import OrderModel, ProductModel

ACTIVE_STATUSES = {"PENDING", "ADDRESS_CONFIRMED", "PAYMENT_PENDING", "CONFIRMED", "PACKING", "OUT_FOR_DELIVERY"}
LOW_STOCK_THRESHOLD = 10


def get_dashboard_summary() -> dict:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        todays_orders = db.query(OrderModel).filter(OrderModel.created_at >= today_start).all()
        todays_revenue = sum(
            order.total for order in todays_orders if order.status not in {"CANCELLED", "PENDING"}
        )

        pending_orders = db.query(OrderModel).filter(OrderModel.status.in_(ACTIVE_STATUSES)).count()

        products = db.query(ProductModel).all()
        low_stock = [
            {"id": p.id, "name": p.name, "stock_quantity": p.stock_quantity}
            for p in products
            if p.stock_quantity <= LOW_STOCK_THRESHOLD
        ]
        out_of_stock_count = sum(1 for p in products if not p.in_stock)

        return {
            "todays_order_count": len(todays_orders),
            "todays_revenue": round(todays_revenue, 2),
            "pending_orders": pending_orders,
            "total_products": len(products),
            "out_of_stock_count": out_of_stock_count,
            "low_stock_products": low_stock,
        }
    finally:
        db.close()
