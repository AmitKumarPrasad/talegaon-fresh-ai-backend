from app.db import SessionLocal
from app.models import OrderItemModel, OrderModel, ProductModel


class InsufficientStockError(ValueError):
    """Raised when an order cannot reserve its requested inventory."""


def create_order(customer_id: str, cart: dict, status: str = "PENDING") -> int:
    db = SessionLocal()
    try:
        order = OrderModel(customer_id=customer_id, total=cart["total"], status=status)
        db.add(order)
        db.flush()
        for item in cart["items"]:
            product = db.query(ProductModel).filter(ProductModel.name.ilike(item["product"])).first()
            if not product or not product.in_stock:
                raise InsufficientStockError(f"Product out of stock: {item['product']}")
            quantity = item["quantity"]
            updated = (
                db.query(ProductModel)
                .filter(
                    ProductModel.id == product.id,
                    ProductModel.stock_quantity >= quantity,
                    ProductModel.in_stock.is_(True),
                )
                .update(
                    {ProductModel.stock_quantity: ProductModel.stock_quantity - quantity},
                    synchronize_session=False,
                )
            )
            if updated != 1:
                raise InsufficientStockError(f"Insufficient stock: {product.name}")
            product = db.get(ProductModel, product.id)
            product.in_stock = product.stock_quantity > 0
            db.add(OrderItemModel(
                order_id=order.id,
                product_name=product.name,
                quantity=quantity,
                unit_price=product.price,
                line_total=item["line_total"],
            ))
        db.commit()
        db.refresh(order)
        return order.id
    finally:
        db.close()
