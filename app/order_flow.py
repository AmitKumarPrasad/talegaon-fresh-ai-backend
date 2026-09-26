import os
from app.db import SessionLocal
from app.models import ProductModel
from app.order_parser import extract_order
from app.order_service import validate_cart
from app.order_repository import create_order

def lookup_prices() -> dict[str, float]:
    db = SessionLocal()
    try:
        rows = db.query(ProductModel).filter(ProductModel.in_stock.is_(True)).all()
        return {row.name: row.price for row in rows}
    finally:
        db.close()

def process_order_message(customer_id: str, message: str) -> dict:
    parsed = extract_order(message)
    items = parsed.get("items", [])
    if not items:
        return {"status": "needs_clarification", "message": "Please send the product name and quantity, for example: 2 kg tomato, 1 kg potato."}

    prices = lookup_prices()
    cart = validate_cart(items, prices)
    if not cart["items"]:
        return {"status": "needs_clarification", "message": "I could not match those products with today's catalog. Please send the product name and quantity."}
    if not cart["eligible"]:
        return {"status": "minimum_not_met", "cart": cart, "message": cart["message"]}

    order_id = create_order(customer_id, cart)
    return {
        "status": "order_created",
        "order_id": order_id,
        "cart": cart,
        "message": f"✅ Order #{order_id} created. Your total is ₹{cart['total']:.2f}. Please reply with your delivery address.",
    }
