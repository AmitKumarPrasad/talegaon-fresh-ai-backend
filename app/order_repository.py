from app.db import SessionLocal
from app.models import OrderItemModel, OrderModel

def create_order(customer_id: str, cart: dict, status: str = "PENDING") -> int:
    db = SessionLocal()
    try:
        order = OrderModel(customer_id=customer_id, total=cart["total"], status=status)
        db.add(order)
        db.flush()
        for item in cart["items"]:
            db.add(OrderItemModel(
                order_id=order.id,
                product_name=item["product"],
                quantity=item["quantity"],
                unit_price=item["unit_price"],
                line_total=item["line_total"],
            ))
        db.commit()
        db.refresh(order)
        return order.id
    finally:
        db.close()
