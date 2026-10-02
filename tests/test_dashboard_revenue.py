from datetime import date, datetime
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.admin_dashboard import get_dashboard_summary
from app.db import Base
from app.models import OrderModel


def test_revenue_excludes_unpaid_orders_and_uses_indian_day_boundaries():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        for status, method, verified, total in [
            ("PAYMENT_PENDING", "UPI", None, 100),
            ("CONFIRMED", "UPI", None, 200),
            ("CONFIRMED", "UPI", datetime(2026, 10, 1, 19), 300),
            ("CONFIRMED", "COD", None, 400),
            ("DELIVERED", "COD", None, 500),
            ("CANCELLED", "UPI", datetime(2026, 10, 1, 19), 600),
        ]:
            db.add(OrderModel(customer_id="9876543210", status=status, payment_method=method,
                              payment_verified_at=verified, total=total, created_at=datetime(2026, 10, 1, 18, 30)))
        # Just before India's midnight, and exactly at the next midnight.
        for created in [datetime(2026, 10, 1, 18, 29, 59), datetime(2026, 10, 2, 18, 30)]:
            db.add(OrderModel(customer_id="9876543210", status="DELIVERED", payment_method="COD", total=900, created_at=created))
        db.commit()
    with patch("app.admin_dashboard.SessionLocal", factory):
        summary = get_dashboard_summary(date(2026, 10, 2))
    assert summary["period_order_count"] == 6
    assert summary["period_revenue"] == 800
    assert summary["daily_breakdown"] == [{"date": "2026-10-02", "order_count": 6, "revenue": 800}]
    engine.dispose()
