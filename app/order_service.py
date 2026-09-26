import os
from app.cart import calculate_cart

ALLOWED_MINIMUMS = {199, 299, 499}

def minimum_order_value() -> float:
    value = int(os.getenv("MIN_ORDER_VALUE", "199"))
    if value not in ALLOWED_MINIMUMS:
        raise ValueError("MIN_ORDER_VALUE must be 199, 299, or 499")
    return float(value)

def validate_cart(items: list[dict], prices: dict[str, float]) -> dict:
    cart = calculate_cart(items, prices)
    minimum = minimum_order_value()
    cart["minimum_order_value"] = minimum
    cart["eligible"] = cart["total"] >= minimum
    if not cart["eligible"]:
        cart["message"] = f"Minimum order value is ₹{int(minimum)}. Please add ₹{int(minimum - cart['total'])} more."
    return cart
