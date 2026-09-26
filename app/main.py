import os
import re
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from app.catalog import product_menu
from app.menu import MENU, menu_response
from app.openai_service import generate_reply
from app.order_details import get_customer_order, update_address, update_payment
from app.order_flow import process_order_message
from app.seller_notification import notify_seller
from app.state import get_state, reset_state
from app.whatsapp import send_text_message

load_dotenv()
app = FastAPI(title="Talegaon Fresh AI Agent", version="0.5.0")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")


@app.get("/")
def health() -> dict:
    return {"service": "Talegaon Fresh AI Agent", "status": "running"}


@app.get("/menu")
def get_menu() -> dict:
    return {"menu": MENU}


@app.get("/products")
def get_products() -> dict:
    return {"products": product_menu()}


@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == VERIFY_TOKEN:
        return PlainTextResponse(params.get("hub.challenge") or "")
    return PlainTextResponse("Verification failed", status_code=403)


def extract_message(body: dict) -> tuple[str | None, str | None]:
    try:
        value = body["entry"][0]["changes"][0]["value"]
        message = value["messages"][0]
        return message.get("from"), message.get("text", {}).get("body")
    except (KeyError, IndexError, TypeError):
        return None, None


def _payment_method(message: str) -> str | None:
    value = message.strip().lower()
    if value in {"1", "upi", "pay by upi", "online", "2 upi"}:
        return "UPI"
    if value in {"2", "cod", "cash", "cash on delivery", "cash on delivery (cod)"}:
        return "COD"
    return None


def _order_id(message: str) -> int | None:
    match = re.search(r"\\b(?:order\\s*(?:id|#)?\\s*)?(\\d+)\\b", message, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _order_status_message(order: dict) -> str:
    payment = order["payment_method"] or "Not selected"
    return (
        f"📦 Order #{order['order_id']}\\n"
        f"Status: {order['status']}\\n"
        f"Total: ₹{order['total']:.2f}\\n"
        f"Payment: {payment}\\n"
        f"Address: {order['address'] or 'Not provided'}"
    )


def handle_conversation(customer_id: str, message: str) -> str:
    state = get_state(customer_id)
    value = message.strip()
    lower = value.lower()

    if lower in {"hi", "hello", "hey", "start", "menu"}:
        reset_state(customer_id)
        return MENU

    # State-specific input must be handled before numeric menu options.
    if state.step == "order_status":
        order_id = _order_id(value)
        if order_id is None:
            return "Please send a valid numeric Order ID, for example: 123."
        order = get_customer_order(order_id, customer_id)
        state.status_order_lookup = False
        state.step = "menu"
        if not order:
            return "❌ Order not found. Please check the Order ID and make sure it belongs to your WhatsApp number."
        return _order_status_message(order)

    if state.step == "address":
        if len(value) < 10:
            return "Please send your complete delivery address, including area/locality and PIN code."
        order_id = state.pending_order_id
        if not order_id or not update_address(order_id, value):
            reset_state(customer_id)
            return "❌ I could not update the pending order. Please start again by replying 1."
        state.step = "payment"
        return f"📍 Address saved for Order #{order_id}.\\n\\nChoose payment method:\\n1️⃣ UPI\\n2️⃣ Cash on Delivery"

    if state.step == "payment":
        method = _payment_method(value)
        if not method:
            return "Please reply with 1 for UPI or 2 for Cash on Delivery."
        order_id = state.pending_order_id
        if not order_id or not update_payment(order_id, method):
            reset_state(customer_id)
            return "❌ I could not update the pending order. Please start again by replying 1."
        order = get_customer_order(order_id, customer_id)
        if not order:
            reset_state(customer_id)
            return "❌ Order could not be loaded. Please contact us."
        if method == "COD":
            notify_seller(order_id, customer_id, order["total"], order["address"] or "", method)
            state.step = "menu"
            state.pending_order_id = None
            return f"✅ Order #{order_id} confirmed!\\nTotal: ₹{order['total']:.2f}\\nPayment: Cash on Delivery\\n\\nWe will prepare your order and deliver it to you."
        state.step = "payment_pending"
        return f"💳 Order #{order_id} is awaiting UPI payment.\\nTotal: ₹{order['total']:.2f}\\n\\nUPI payment link/verification will be connected in the next payment integration step. Please do not mark the order as paid manually."

    if state.step == "payment_pending":
        return "💳 Your order is awaiting UPI payment verification. We will confirm it after the payment integration is connected."

    if value == "1":
        reset_state(customer_id)
        state = get_state(customer_id)
        state.step = "products"
        return "🛒 Let's place your order!\\n\\nSend your items and quantities. Example:\\n2 kg tomato, 1 kg potato, 500 g carrot"

    if value == "2":
        state.step = "products"
        return f"🥦 Today's Products\\n\\n{product_menu()}\\n\\nSend product name and quantity to order."

    if value == "3":
        state.status_order_lookup = True
        state.step = "order_status"
        return "🔎 Please send your Talegaon Fresh Order ID to check its status."

    if value == "4":
        return "🚚 Delivery Information\\n\\nWe provide home delivery in Talegaon and nearby areas. Delivery details are confirmed during your order.\\n\\nReply 1 to place an order."

    if value == "5":
        return "💳 Payment Options\\n\\n1️⃣ UPI\\n2️⃣ Cash on Delivery\\n\\nYour payment method will be confirmed before the order is completed."

    if value == "6":
        state.step = "support"
        return "👤 Our team will assist you. Please send your question and we will respond as soon as possible."

    if state.step == "products":
        result = process_order_message(customer_id, value)
        if result["status"] == "order_created":
            state.pending_order_id = result["order_id"]
            state.step = "address"
        return result["message"]

    if state.step == "support":
        return generate_reply(value)

    result = process_order_message(customer_id, value)
    if result["status"] == "order_created":
        state.pending_order_id = result["order_id"]
        state.step = "address"
    return result["message"]

