import json
import logging
import os
import re

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.admin_orders import get_admin_order, list_orders
from app.catalog import product_menu
from app.config import validate_production_config
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
from app.seed import seed_products
from app.price_service import (
    bulk_update_product_prices,
    list_current_prices,
    price_history,
    update_product_price,
)
from app.payment_service import PaymentError, create_payment_link, extract_paid_event, verify_webhook_signature
from app.seller_notification import notify_seller
from app.state import get_state, reset_state
from app.webhook_idempotency import claim_event
from app.whatsapp import send_text_message

load_dotenv()
logger = logging.getLogger(__name__)
app = FastAPI(title="Talegaon Fresh AI Agent", version="0.7.0")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
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
    return {"products": product_menu()}


@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == VERIFY_TOKEN:
        return PlainTextResponse(params.get("hub.challenge") or "")
    return PlainTextResponse("Verification failed", status_code=403)



class PriceUpdateRequest(BaseModel):
    price: float = Field(gt=0)
    in_stock: bool | None = None


class BulkPriceUpdateItem(BaseModel):
    product_id: int = Field(gt=0)
    price: float = Field(gt=0)
    in_stock: bool | None = None


class BulkPriceUpdateRequest(BaseModel):
    prices: list[BulkPriceUpdateItem] = Field(min_length=1)


def _admin_authorized(request: Request) -> bool:
    configured = os.getenv("ADMIN_API_TOKEN")
    return bool(configured) and request.headers.get("X-Admin-Token") == configured


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
        product = update_product_price(product_id, payload.price, payload.in_stock)
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
    body = await request.json()
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

    if not claim_event("razorpay", event_id):
        logger.info("Razorpay webhook duplicate event_id=%s", event_id)
        return {"status": "duplicate"}

    confirmed = confirm_upi_payment(
        order_id=order_id,
        payment_link_id=event["payment_link_id"],
        payment_id=event["payment_id"],
        event_id=event_id,
        amount_paise=event["amount"],
    )

    if not confirmed:
        logger.info(
            "Razorpay payment already processed or could not be confirmed order_id=%s payment_id=%s event_id=%s",
            order_id,
            event["payment_id"],
            event_id,
        )
        return {"status": "processed"}

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
        "Razorpay payment confirmed successfully order_id=%s amount_paise=%s payment_id=%s event_id=%s",
        order_id,
        event["amount"],
        event["payment_id"],
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
