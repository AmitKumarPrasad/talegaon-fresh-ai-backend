from datetime import date, datetime, time, timezone

from app.db import SessionLocal
from app.models import ProductModel, ProductPriceHistoryModel


def list_current_prices() -> list[dict]:
    db = SessionLocal()
    try:
        rows = db.query(ProductModel).order_by(ProductModel.id).all()
        return [
            {
                "id": row.id,
                "name": row.name,
                "unit": row.unit,
                "price": row.price,
                "in_stock": row.in_stock,
            }
            for row in rows
        ]
    finally:
        db.close()


def update_product_price(product_id: int, price: float, in_stock: bool | None = None) -> dict | None:
    if price <= 0:
        raise ValueError("Price must be greater than zero.")

    db = SessionLocal()
    try:
        product = db.get(ProductModel, product_id)
        if not product:
            return None

        product.price = price
        if in_stock is not None:
            product.in_stock = in_stock

        now = datetime.now(timezone.utc)
        db.add(
            ProductPriceHistoryModel(
                product_id=product.id,
                price=price,
                effective_date=now,
                created_at=now,
            )
        )
        db.commit()
        db.refresh(product)

        return {
            "id": product.id,
            "name": product.name,
            "unit": product.unit,
            "price": product.price,
            "in_stock": product.in_stock,
        }
    finally:
        db.close()


def price_history(product_id: int, limit: int = 30) -> list[dict]:
    limit = max(1, min(limit, 100))
    db = SessionLocal()
    try:
        rows = (
            db.query(ProductPriceHistoryModel)
            .filter(ProductPriceHistoryModel.product_id == product_id)
            .order_by(ProductPriceHistoryModel.effective_date.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "price": row.price,
                "effective_date": row.effective_date.isoformat(),
            }
            for row in rows
        ]
    finally:
        db.close()
