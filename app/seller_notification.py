import os
from app.whatsapp import send_text_message


def notify_seller(order_id: int, customer_id: str, total: float, address: str, payment_method: str) -> dict:
    seller_number = os.getenv("SELLER_WHATSAPP_NUMBER")
    if not seller_number:
        return {"status": "skipped", "reason": "SELLER_WHATSAPP_NUMBER is not configured"}
    message = (
        f"🛒 New Talegaon Fresh Order #{order_id}\\n"
        f"Customer: {customer_id}\\n"
        f"Total: ₹{total:.2f}\\n"
        f"Payment: {payment_method}\\n"
        f"Address: {address}"
    )
    return send_text_message(seller_number, message)
