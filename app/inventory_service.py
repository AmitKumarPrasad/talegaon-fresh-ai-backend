from app.db import SessionLocal
from app.models import ProductModel


def list_inventory() -> list[dict]:
    db = SessionLocal()
    try:
        rows = db.query(ProductModel).order_by(ProductModel.id).all()
        return [
            {
                "id": row.id,
                "name": row.name,
                "unit": row.unit,
                "stock_quantity": row.stock_quantity,
                "in_stock": row.in_stock,
            }
            for row in rows
        ]
    finally:
        db.close()


def update_inventory(product_id: int, stock_quantity: int) -> dict | None:
    if stock_quantity < 0:
        raise ValueError("Stock quantity cannot be negative.")

    db = SessionLocal()
    try:
        product = db.get(ProductModel, product_id)
        if not product:
            return None
        product.stock_quantity = stock_quantity
        product.in_stock = stock_quantity > 0
        db.commit()
        db.refresh(product)
        return {
            "id": product.id,
            "name": product.name,
            "unit": product.unit,
            "stock_quantity": product.stock_quantity,
            "in_stock": product.in_stock,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
