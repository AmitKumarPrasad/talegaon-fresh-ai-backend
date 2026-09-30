import json
import logging
import os
import re
import hmac

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from app.admin_orders import get_admin_order, list_orders
from app.admin_dashboard import get_dashboard_summary
from app.customer_api import router as customer_router
from app.catalog import product_menu
from app.config import get_cors_allowed_origins, validate_production_config
from app.delivery_service import (
    add_message_by_delivery,
    assign_delivery_person,
    get_delivery_order_summary,
    list_messages_for_delivery,
    update_delivery_location,
)
from app.menu import MENU
from app.openai_service import generate_reply
from app.order_details import (
    confirm_upi_payment,
    get_customer_order,
    save_payment_link,
    transition_order_status,
    update_address,
    update_payment,
)
from app.order_flow import process_order_message
from app.order_status import list_status_history
from app.seed import seed_products
from app.price_service import (
    bulk_update_product_prices,
    create_product,
    delete_product,
    list_current_prices,
    price_history,
    update_product_price,
)
from app.inventory_service import list_inventory, update_inventory
from app.payment_service import PaymentError, create_payment_link, extract_paid_event, verify_webhook_signature
from app.seller_notification import notify_seller
from app.state import get_state, reset_state
from app.webhook_idempotency import claim_event
from app.whatsapp import send_text_message
from app.rate_limiter import enforce_rate_limit
from app.whatsapp_webhook_security import verify_meta_signature

load_dotenv()
logger = logging.getLogger(__name__)
app = FastAPI(title="Talegaon Fresh AI Agent", version="0.8.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Admin-Token"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    rate_limit_response = await enforce_rate_limit(request)
    if rate_limit_response is not None:
        return rate_limit_response
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/auth/") or request.url.path.startswith("/customers/me"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    return response


app.include_router(customer_router)
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET")
validate_production_config()


@app.get("/health")
def health() -> dict:
    return {"service": "Talegaon Fresh AI Agent", "status": "running"}


@app.get("/")
def root() -> dict:
    return health()


@app.get("/menu")
def get_menu() -> dict:
    return {"menu": MENU}


@app.get("/products")
def get_products() -> dict:
    return {"products": list_current_prices()}


@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and VERIFY_TOKEN and hmac.compare_digest(params.get("hub.verify_token") or "", VERIFY_TOKEN):
        return PlainTextResponse(params.get("hub.challenge") or "")
    return PlainTextResponse("Verification failed", status_code=403)



class PriceUpdateRequest(BaseModel):
    price: float = Field(gt=0)
    in_stock: bool | None = None
    image_url: str | None = Field(default=None, max_length=500)


class CreateProductRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    unit: str = Field(min_length=1, max_length=30)
    price: float = Field(gt=0)
    stock_quantity: int = Field(default=0, ge=0)
    image_url: str | None = Field(default=None, max_length=500)


class InventoryUpdateRequest(BaseModel):
    stock_quantity: int = Field(ge=0)


class BulkPriceUpdateItem(BaseModel):
    product_id: int = Field(gt=0)
    price: float = Field(gt=0)
    in_stock: bool | None = None


class BulkPriceUpdateRequest(BaseModel):
    prices: list[BulkPriceUpdateItem] = Field(min_length=1)


def _admin_authorized(request: Request) -> bool:
    configured = os.getenv("ADMIN_API_TOKEN")
    return bool(configured) and hmac.compare_digest(request.headers.get("X-Admin-Token", ""), configured)


@app.get("/admin/dashboard")
async def admin_dashboard(request: Request):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    return get_dashboard_summary()


@app.get("/admin/inventory")
async def admin_inventory(request: Request):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    return {"products": list_inventory()}


@app.put("/admin/inventory/{product_id}")
async def admin_update_inventory(
    product_id: int,
    payload: InventoryUpdateRequest,
    request: Request,
):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    try:
        product = update_inventory(product_id, payload.stock_quantity)
    except ValueError as exc:
        return PlainTextResponse(str(exc), status_code=400)
    if not product:
        return PlainTextResponse("Product not found", status_code=404)
    return product


@app.get("/admin/prices")
async def admin_prices(request: Request):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    return {"products": list_current_prices()}


@app.post("/admin/products/seed")
async def admin_seed_products(request: Request):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    seed_products()
    return {"products": list_current_prices(), "message": "Missing catalog products were initialized."}


@app.post("/admin/products")
async def admin_create_product(payload: CreateProductRequest, request: Request):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    try:
        product = create_product(
            payload.name, payload.unit, payload.price, payload.stock_quantity, payload.image_url
        )
    except ValueError as exc:
        return PlainTextResponse(str(exc), status_code=400)
    return product


@app.delete("/admin/products/{product_id}")
async def admin_delete_product(product_id: int, request: Request):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    if not delete_product(product_id):
        return PlainTextResponse("Product not found", status_code=404)
    return {"status": "deleted"}


@app.put("/admin/prices/bulk")
async def admin_bulk_update_prices(
    payload: BulkPriceUpdateRequest,
    request: Request,
):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    try:
        products = bulk_update_product_prices(
            [item.model_dump() for item in payload.prices]
        )
    except ValueError as exc:
        return PlainTextResponse(str(exc), status_code=400)
    return {"products": products, "message": "Daily prices updated successfully."}


@app.put("/admin/prices/{product_id}")
async def admin_update_price(product_id: int, payload: PriceUpdateRequest, request: Request):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    try:
        product = update_product_price(product_id, payload.price, payload.in_stock, payload.image_url)
    except ValueError as exc:
        return PlainTextResponse(str(exc), status_code=400)
    if not product:
        return PlainTextResponse("Product not found", status_code=404)
    return product


class OrderStatusUpdateRequest(BaseModel):
    status: str = Field(min_length=1, max_length=30)


@app.get("/admin/orders")
async def admin_orders(
    request: Request,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    if status and status.upper() not in {
        "PENDING",
        "ADDRESS_CONFIRMED",
        "PAYMENT_PENDING",
        "CONFIRMED",
        "PACKING",
        "OUT_FOR_DELIVERY",
        "DELIVERED",
        "CANCELLED",
    }:
        return PlainTextResponse("Invalid order status", status_code=400)
    return {
        "orders": list_orders(status=status, limit=limit, offset=offset),
        "limit": min(max(limit, 1), 100),
        "offset": max(offset, 0),
    }


@app.get("/admin/orders/{order_id}")
async def admin_order(order_id: int, request: Request):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    order = get_admin_order(order_id)
    if not order:
        return PlainTextResponse("Order not found", status_code=404)
    return order


@app.get("/admin/orders/{order_id}/status-history")
async def admin_order_status_history(order_id: int, request: Request):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    order = get_admin_order(order_id)
    if not order:
        return PlainTextResponse("Order not found", status_code=404)
    return {"order_id": order_id, "history": list_status_history(order_id)}


class AssignDeliveryRequest(BaseModel):
    delivery_person_name: str = Field(min_length=1, max_length=100)
    delivery_person_phone: str = Field(min_length=7, max_length=30)


@app.patch("/admin/orders/{order_id}/delivery")
async def admin_assign_delivery(order_id: int, payload: AssignDeliveryRequest, request: Request):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    result = assign_delivery_person(order_id, payload.delivery_person_name, payload.delivery_person_phone)
    if not result:
        return PlainTextResponse("Order not found", status_code=404)
    base_url = os.getenv("PUBLIC_BASE_URL", "https://talegaon-fresh-ai-backend.onrender.com")
    delivery_link = f"{base_url}/delivery/{result['delivery_token']}"
    try:
        send_text_message(
            payload.delivery_person_phone,
            f"Hi {payload.delivery_person_name}, you're assigned to deliver Talegaon Fresh Order #{order_id}. "
            f"Open this link to share your live location and chat with the customer: {delivery_link}",
        )
    except Exception:
        logger.exception("Failed to notify delivery person for order_id=%s", order_id)
    result.pop("delivery_token", None)
    return {**result, "delivery_link": delivery_link}


@app.patch("/admin/orders/{order_id}/status")
async def admin_update_order_status(
    order_id: int,
    payload: OrderStatusUpdateRequest,
    request: Request,
):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)

    order = get_admin_order(order_id)
    if not order:
        return PlainTextResponse("Order not found", status_code=404)

    if not transition_order_status(order_id, payload.status):
        return PlainTextResponse(
            f"Invalid status transition from {order['status']} to {payload.status.upper()}",
            status_code=409,
        )

    return get_admin_order(order_id)


@app.get("/admin/prices/{product_id}/history")
async def admin_price_history(product_id: int, request: Request, limit: int = 30):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    return {"product_id": product_id, "history": price_history(product_id, limit)}


class DeliveryLocationRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class DeliveryMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


@app.get("/delivery/{token}/summary")
async def delivery_order_summary(token: str):
    summary = get_delivery_order_summary(token)
    if not summary:
        return PlainTextResponse("Invalid or expired delivery link", status_code=404)
    return summary


@app.post("/delivery/{token}/location")
async def delivery_update_location(token: str, payload: DeliveryLocationRequest):
    try:
        updated = update_delivery_location(token, payload.lat, payload.lng)
    except ValueError as exc:
        return PlainTextResponse(str(exc), status_code=400)
    if not updated:
        return PlainTextResponse("Invalid or expired delivery link", status_code=404)
    return {"status": "updated"}


@app.get("/delivery/{token}/messages")
async def delivery_list_messages(token: str):
    messages = list_messages_for_delivery(token)
    if messages is None:
        return PlainTextResponse("Invalid or expired delivery link", status_code=404)
    return {"messages": messages}


@app.post("/delivery/{token}/messages")
async def delivery_send_message(token: str, payload: DeliveryMessageRequest):
    message = add_message_by_delivery(token, payload.message)
    if message is None:
        return PlainTextResponse("Invalid or expired delivery link", status_code=404)
    return message


@app.get("/delivery/{token}", response_class=HTMLResponse)
async def delivery_page(token: str):
    summary = get_delivery_order_summary(token)
    if not summary:
        return HTMLResponse("<h2>Invalid or expired delivery link.</h2>", status_code=404)
    return HTMLResponse(_DELIVERY_PAGE_HTML.replace("__TOKEN__", token))


_DELIVERY_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Talegaon Fresh — Delivery</title>
<style>
  body { font-family: -apple-system, Roboto, Arial, sans-serif; margin: 0; background: #F7FAF5; color: #1a1a1a; }
  .header { background: #168447; color: white; padding: 18px 20px; font-weight: 800; font-size: 18px; }
  .card { background: white; margin: 14px; padding: 16px; border-radius: 14px; box-shadow: 0 2px 10px rgba(0,0,0,0.06); }
  button { background: #168447; color: white; border: none; padding: 12px 18px; border-radius: 10px; font-weight: 700; font-size: 15px; }
  button:disabled { background: #99c7ac; }
  #status { margin-top: 10px; font-size: 13px; color: #555; }
  .chat { max-height: 260px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
  .bubble { padding: 8px 12px; border-radius: 12px; max-width: 80%; font-size: 14px; }
  .customer { background: #EAF6EA; align-self: flex-start; }
  .delivery { background: #168447; color: white; align-self: flex-end; }
  input[type=text] { flex: 1; padding: 10px; border-radius: 10px; border: 1px solid #ddd; font-size: 14px; }
  .row { display: flex; gap: 8px; margin-top: 10px; }
  ul { padding-left: 18px; margin: 6px 0; }
</style>
</head>
<body>
  <div class="header">Talegaon Fresh — Delivery</div>
  <div class="card" id="order-card">Loading order...</div>
  <div class="card">
    <b>Live Location</b>
    <div id="status">Not sharing yet.</div>
    <div style="margin-top:10px;"><button id="share-btn">Share My Location</button></div>
  </div>
  <div class="card">
    <b>Chat with Customer</b>
    <div class="chat" id="chat"></div>
    <div class="row">
      <input type="text" id="msg-input" placeholder="Type a message...">
      <button id="send-btn">Send</button>
    </div>
  </div>
<script>
const token = "__TOKEN__";
const base = window.location.origin;
let watchId = null;

async function loadOrder() {
  const res = await fetch(`${base}/delivery/${token}/summary`);
  if (!res.ok) { document.getElementById('order-card').innerText = 'Invalid or expired link.'; return; }
  const data = await res.json();
  let itemsHtml = data.items.map(i => `<li>${i.quantity} x ${i.name}</li>`).join('');
  document.getElementById('order-card').innerHTML =
    `<b>Order #${data.order_id}</b> — ${data.status}<br>` +
    `Address: ${data.address || 'N/A'}<br>Total: Rs.${data.total}<br>Payment: ${data.payment_method || 'N/A'}` +
    `<ul>${itemsHtml}</ul>`;
}

function startSharing() {
  if (!navigator.geolocation) { document.getElementById('status').innerText = 'Geolocation not supported.'; return; }
  document.getElementById('share-btn').disabled = true;
  watchId = navigator.geolocation.watchPosition(async (pos) => {
    const { latitude, longitude } = pos.coords;
    document.getElementById('status').innerText = `Sharing... last update ${new Date().toLocaleTimeString()}`;
    await fetch(`${base}/delivery/${token}/location`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat: latitude, lng: longitude }),
    });
  }, (err) => {
    document.getElementById('status').innerText = 'Location error: ' + err.message;
  }, { enableHighAccuracy: true, maximumAge: 10000, timeout: 15000 });
}

async function loadMessages() {
  const res = await fetch(`${base}/delivery/${token}/messages`);
  if (!res.ok) return;
  const data = await res.json();
  const chat = document.getElementById('chat');
  chat.innerHTML = data.messages.map(m =>
    `<div class="bubble ${m.sender === 'delivery' ? 'delivery' : 'customer'}">${m.message}</div>`
  ).join('');
  chat.scrollTop = chat.scrollHeight;
}

async function sendMessage() {
  const input = document.getElementById('msg-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  await fetch(`${base}/delivery/${token}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: text }),
  });
  loadMessages();
}

document.getElementById('share-btn').addEventListener('click', startSharing);
document.getElementById('send-btn').addEventListener('click', sendMessage);
document.getElementById('msg-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') sendMessage(); });

loadOrder();
loadMessages();
setInterval(loadMessages, 6000);
</script>
</body>
</html>"""


def extract_message(body: dict) -> tuple[str | None, str | None, str | None]:
    try:
        value = body["entry"][0]["changes"][0]["value"]
        message = value["messages"][0]
        return (
            message.get("from"),
            message.get("text", {}).get("body"),
            message.get("id"),
        )
    except (KeyError, IndexError, TypeError):
        return None, None, None


def _payment_method(message: str) -> str | None:
    value = message.strip().lower()
    if value in {"1", "upi", "pay by upi", "online", "2 upi"}:
        return "UPI"
    if value in {"2", "cod", "cash", "cash on delivery", "cash on delivery (cod)"}:
        return "COD"
    return None


def _order_id(message: str) -> int | None:
    match = re.search(r"\b(?:order\s*(?:id|#)?\s*)?(\d+)\b", message, re.IGNORECASE)
    return int(match.group(1)) if match else None


def _order_status_message(order: dict) -> str:
    payment = order["payment_method"] or "Not selected"
    return (
        f"📦 Order #{order['order_id']}\n"
        f"Status: {order['status']}\n"
        f"Total: ₹{order['total']:.2f}\n"
        f"Payment: {payment}\n"
        f"Address: {order['address'] or 'Not provided'}"
    )


def handle_conversation(customer_id: str, message: str) -> str:
    state = get_state(customer_id)
    value = message.strip()
    lower = value.lower()

    if lower in {"hi", "hello", "hey", "start", "menu"}:
        reset_state(customer_id)
        return MENU

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
        return f"📍 Address saved for Order #{order_id}.\n\nChoose payment method:\n1️⃣ UPI\n2️⃣ Cash on Delivery"

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
            try:
                notify_seller(
                    order_id,
                    customer_id,
                    order["total"],
                    order["address"] or "",
                    method,
                )
            except Exception:
                logger.exception(
                    "COD order confirmed but seller notification failed order_id=%s",
                    order_id,
                )
            state.step = "menu"
            state.pending_order_id = None
            return (
                f"✅ Order #{order_id} confirmed!\n"
                f"Total: ₹{order['total']:.2f}\n"
                "Payment: Cash on Delivery\n\n"
                "We will prepare your order and deliver it to you. "
                "Please keep the exact amount ready at delivery."
            )

        try:
            link = create_payment_link(order_id, order["total"], customer_id)
            save_payment_link(order_id, link["id"], link["short_url"])
        except PaymentError:
            return "❌ UPI payment is temporarily unavailable. Please choose 2 for Cash on Delivery or try again later."

        state.step = "payment_pending"
        return (
            f"💳 Order #{order_id} is ready for UPI payment.\n"
            f"Total: ₹{order['total']:.2f}\n\n"
            f"Pay securely using this link:\n{link['short_url']}\n\n"
            "After payment, your order will be confirmed automatically."
        )

    if state.step == "payment_pending":
        return "💳 Your UPI payment link is still pending. Please complete the payment using the link sent above. Your order will be confirmed automatically after Razorpay verifies the payment."

    if value == "1":
        reset_state(customer_id)
        state = get_state(customer_id)
        state.step = "products"
        return "🛒 Let's place your order!\n\nSend your items and quantities. Example:\n2 kg tomato, 1 kg potato, 500 g carrot"

    if value == "2":
        state.step = "products"
        return f"🥦 Today's Products\n\n{product_menu()}\n\nSend product name and quantity to order."

    if value == "3":
        state.status_order_lookup = True
        state.step = "order_status"
        return "🔎 Please send your Talegaon Fresh Order ID to check its status."

    if value == "4":
        return "🚚 Delivery Information\n\nWe provide home delivery in Talegaon and nearby areas. Delivery details are confirmed during your order.\n\nReply 1 to place an order."

    if value == "5":
        return "💳 Payment Options\n\n1️⃣ UPI\n2️⃣ Cash on Delivery\n\nYour payment method will be confirmed before the order is completed."

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


@app.post("/webhook")
async def receive_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_meta_signature(raw_body, signature, WHATSAPP_APP_SECRET):
        logger.warning("WhatsApp webhook rejected: invalid signature")
        return PlainTextResponse("Invalid signature", status_code=403)
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        return PlainTextResponse("Invalid JSON", status_code=400)
    customer_id, message, message_id = extract_message(body)
    if not customer_id or not message:
        return {"status": "ignored"}
    if not message_id:
        return {"status": "ignored", "reason": "missing_message_id"}
    if not claim_event("whatsapp", message_id):
        return {"status": "duplicate"}

    reply = handle_conversation(customer_id, message)
    send_text_message(customer_id, reply)
    return {"status": "received"}


@app.post("/razorpay/webhook")
async def razorpay_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    if not verify_webhook_signature(raw_body, signature):
        logger.warning(
            "Razorpay webhook rejected: invalid signature; signature_present=%s body_bytes=%s",
            bool(signature),
            len(raw_body),
        )
        return PlainTextResponse("Invalid signature", status_code=400)

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.warning("Razorpay webhook rejected: invalid JSON")
        return PlainTextResponse("Invalid JSON", status_code=400)

    event = extract_paid_event(payload)
    if not event:
        logger.info(
            "Razorpay webhook ignored: unsupported or incomplete event type=%s event_id=%s",
            payload.get("event"),
            payload.get("id"),
        )
        return {"status": "ignored"}

    event_id = event.get("event_id")
    if not event_id:
        logger.warning(
            "Razorpay webhook rejected: missing event ID event_type=%s",
            event.get("event"),
        )
        return PlainTextResponse("Missing event ID", status_code=400)

    try:
        order_id = int(str(event["reference_id"]).removeprefix("TF-"))
    except (TypeError, ValueError):
        logger.warning(
            "Razorpay webhook ignored: invalid reference_id=%s event_id=%s",
            event.get("reference_id"),
            event_id,
        )
        return {"status": "ignored"}

    if event["event"] != "payment_link.paid" or event["status"] != "captured":
        logger.info(
            "Razorpay webhook ignored: event=%s status=%s order_id=%s event_id=%s",
            event["event"],
            event["status"],
            order_id,
            event_id,
        )
        return {"status": "ignored"}

    order = _order_for_payment(order_id)
    if not order:
        logger.error(
            "Razorpay webhook ignored: order not found order_id=%s event_id=%s",
            order_id,
            event_id,
        )
        return {"status": "ignored"}

    expected_amount = int(round(order["total"] * 100))
    if order["payment_method"] != "UPI":
        logger.error(
            "Razorpay webhook ignored: order payment method is %s order_id=%s",
            order["payment_method"],
            order_id,
        )
        return {"status": "ignored"}

    if event["amount"] != expected_amount:
        logger.error(
            "Razorpay webhook ignored: amount mismatch order_id=%s expected_paise=%s received_paise=%s event_id=%s",
            order_id,
            expected_amount,
            event["amount"],
            event_id,
        )
        return {"status": "ignored"}

    if (
        order["razorpay_payment_link_id"]
        and order["razorpay_payment_link_id"] != event["payment_link_id"]
    ):
        logger.error(
            "Razorpay webhook ignored: payment link mismatch order_id=%s event_id=%s",
            order_id,
            event_id,
        )
        return {"status": "ignored"}

    confirmed = confirm_upi_payment(
        order_id=order_id,
        payment_link_id=event["payment_link_id"],
        payment_id=event["payment_id"],
        event_id=event_id,
        amount_paise=event["amount"],
    )

    if not confirmed:
        logger.info(
            "Razorpay payment already processed or could not be confirmed order_id=%s event_id=%s",
            order_id,
            event_id,
        )
        return {"status": "processed"}

    # Claim only after the payment transaction succeeds. This prevents a transient
    # database failure from permanently consuming a valid provider event.
    claim_event("razorpay", event_id)

    customer_id = order["customer_id"]

    try:
        notify_seller(
            order_id,
            customer_id,
            order["total"],
            order["address"] or "",
            "UPI",
        )
    except Exception:
        logger.exception(
            "Razorpay payment confirmed but seller notification failed order_id=%s",
            order_id,
        )

    try:
        send_text_message(
            customer_id,
            f"✅ Payment received for Order #{order_id}. Your UPI payment is verified and the order is confirmed.\nTotal: ₹{order['total']:.2f}",
        )
    except Exception:
        logger.exception(
            "Razorpay payment confirmed but customer notification failed order_id=%s",
            order_id,
        )

    logger.info(
        "Razorpay payment confirmed successfully order_id=%s amount_paise=%s event_id=%s",
        order_id,
        event["amount"],
        event_id,
    )
    return {"status": "processed"}


def _order_for_payment(order_id: int) -> dict | None:
    from app.order_details import get_order

    return get_order(order_id)


def _customer_for_order(order_id: int) -> str:
    from app.db import SessionLocal
    from app.models import OrderModel

    db = SessionLocal()
    try:
        order = db.get(OrderModel, order_id)
        return order.customer_id if order else ""
    finally:
        db.close()
