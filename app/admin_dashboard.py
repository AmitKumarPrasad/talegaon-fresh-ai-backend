from datetime import date, datetime, time, timedelta, timezone

from app.db import SessionLocal
from app.models import OrderModel, ProductModel

ACTIVE_STATUSES = {"PENDING", "ADDRESS_CONFIRMED", "PAYMENT_PENDING", "CONFIRMED", "PACKING", "OUT_FOR_DELIVERY"}
LOW_STOCK_THRESHOLD = 10


def get_dashboard_summary(start_date: date | None = None, end_date: date | None = None) -> dict:
    db = SessionLocal()
    try:
        today = datetime.now(timezone.utc).date()
        start_date = start_date or today
        end_date = end_date or start_date
        if end_date < start_date:
            raise ValueError("End date cannot be before start date")
        period_start = datetime.combine(start_date, time.min)
        period_end = datetime.combine(end_date + timedelta(days=1), time.min)

        period_orders = db.query(OrderModel).filter(
            OrderModel.created_at >= period_start,
            OrderModel.created_at < period_end,
        ).all()
        period_revenue = sum(
            order.total for order in period_orders if order.status not in {"CANCELLED", "PENDING"}
        )
        daily = {}
        for order in period_orders:
            day = order.created_at.date().isoformat()
            bucket = daily.setdefault(day, {"date": day, "order_count": 0, "revenue": 0.0})
            bucket["order_count"] += 1
            if order.status not in {"CANCELLED", "PENDING"}:
                bucket["revenue"] += order.total

        pending_orders = db.query(OrderModel).filter(OrderModel.status.in_(ACTIVE_STATUSES)).count()

        products = db.query(ProductModel).all()
        low_stock = [
            {"id": p.id, "name": p.name, "stock_quantity": p.stock_quantity}
            for p in products
            if p.stock_quantity <= LOW_STOCK_THRESHOLD
        ]
        out_of_stock_count = sum(1 for p in products if not p.in_stock)

        return {
            "todays_order_count": len(period_orders),
            "todays_revenue": round(period_revenue, 2),
            "period_order_count": len(period_orders),
            "period_revenue": round(period_revenue, 2),
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "daily_breakdown": [
                {**bucket, "revenue": round(bucket["revenue"], 2)}
                for bucket in sorted(daily.values(), key=lambda item: item["date"], reverse=True)
            ],
            "pending_orders": pending_orders,
            "total_products": len(products),
            "out_of_stock_count": out_of_stock_count,
            "low_stock_products": low_stock,
        }
    finally:
        db.close()
