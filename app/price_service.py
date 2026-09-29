from datetime import datetime, timezone

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


def _product_response(product: ProductModel) -> dict:
    return {
        "id": product.id,
        "name": product.name,
        "unit": product.unit,
        "price": product.price,
        "in_stock": product.in_stock,
    }


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
        return _product_response(product)
    finally:
        db.close()


def bulk_update_product_prices(updates: list[dict]) -> list[dict]:
    if not updates:
        raise ValueError("At least one product price is required.")

    product_ids = [int(item["product_id"]) for item in updates]
    if len(product_ids) != len(set(product_ids)):
        raise ValueError("Duplicate product IDs are not allowed.")

    for item in updates:
        if float(item["price"]) <= 0:
            raise ValueError("Price must be greater than zero.")

    db = SessionLocal()
    try:
        products = (
            db.query(ProductModel)
            .filter(ProductModel.id.in_(product_ids))
            .all()
        )
        by_id = {product.id: product for product in products}
        missing = [product_id for product_id in product_ids if product_id not in by_id]
        if missing:
            raise ValueError(
                "Product(s) not found: " + ", ".join(str(product_id) for product_id in missing)
            )

        now = datetime.now(timezone.utc)
        for item in updates:
            product = by_id[int(item["product_id"])]
            product.price = float(item["price"])
            if item.get("in_stock") is not None:
                product.in_stock = bool(item["in_stock"])
            db.add(
                ProductPriceHistoryModel(
                    product_id=product.id,
                    price=product.price,
                    effective_date=now,
                    created_at=now,
                )
            )

        db.commit()
        for product in products:
            db.refresh(product)
        return [_product_response(by_id[product_id]) for product_id in product_ids]
    except Exception:
        db.rollback()
        raise
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
