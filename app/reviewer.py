"""Authenticated reviewer checkout, isolated from fulfillment and accounting."""
import os
import re
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base, SessionLocal


class ReviewerOrderModel(Base):
    __tablename__ = "reviewer_orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(50), index=True)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)


def is_reviewer(phone: str) -> bool:
    # This account still requires its existing hashed PIN and normal JWT checks.
    configured = os.getenv("REVIEWER_CUSTOMER_PHONES", "9579330319")
    return phone in {value.strip() for value in configured.split(",") if value.strip()}


def require_service_area(address: str, phone: str) -> None:
    if is_reviewer(phone):
        return
    pins = re.findall(r"(?<!\d)[1-9]\d{5}(?!\d)", address)
    if not pins or not pins[-1].startswith("41"):
        raise HTTPException(400, "Delivery is currently available across Pune. Enter a valid Pune PIN code.")


def list_orders(phone: str) -> list[dict]:
    with SessionLocal() as db:
        rows = db.query(ReviewerOrderModel).filter_by(customer_id=phone).order_by(ReviewerOrderModel.id.desc()).all()
        return [dict(row.snapshot, order_id=row.id) for row in rows]


def get_order(phone: str, order_id: int) -> dict:
    with SessionLocal() as db:
        row = db.get(ReviewerOrderModel, order_id)
        if not row or row.customer_id != phone:
            raise HTTPException(404, "Demo order not found")
        return dict(row.snapshot, order_id=row.id)


def create_order(db, customer, payload, address, quote, commit=True) -> dict:
    from app.models import ProductModel
    items = []
    for item in payload.items:
        product = db.query(ProductModel).filter(ProductModel.name.ilike(item.name)).first()
        if not product:
            raise HTTPException(400, f"Product not found: {item.name}")
        items.append({"name": product.name, "unit": product.unit, "unit_price": product.price,
                      "quantity": item.quantity, "line_total": round(product.price * item.quantity, 2)})
    now = datetime.now(timezone.utc).isoformat()
    # Instant simulated delivery makes order details and post-delivery suggestions
    # reviewable without involving a live delivery partner or collecting payment.
    snapshot = dict(quote, address=address, items=items, status="DELIVERED", delivery_status="DELIVERED",
                    payment_method="COD", payment_status="PAYMENT_SUCCESS", created_at=now,
                    is_demo=True, messages=[], product_requests=[],
                    history=[{"from_status":"PENDING", "to_status":"CONFIRMED", "created_at":now},
                             {"from_status":"CONFIRMED", "to_status":"DELIVERED", "created_at":now}])
    row = ReviewerOrderModel(customer_id=customer.phone, snapshot=snapshot)
    db.add(row)
    db.flush()
    if commit:
        db.commit()
    db.refresh(row)
    return dict(row.snapshot, order_id=row.id)


def append_entry(phone: str, order_id: int, key: str, entry: dict) -> dict:
    with SessionLocal() as db:
        row = db.get(ReviewerOrderModel, order_id)
        if not row or row.customer_id != phone:
            raise HTTPException(404, "Demo order not found")
        snapshot = dict(row.snapshot)
        entries = list(snapshot.get(key, []))
        entry = dict(entry, id=len(entries) + 1, created_at=datetime.now(timezone.utc).isoformat())
        entries.append(entry)
        snapshot[key] = entries
        row.snapshot = snapshot
        db.commit()
        return entry

