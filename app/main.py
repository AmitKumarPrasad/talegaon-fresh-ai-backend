import json
import logging
import os
import re
import hmac
import uuid
from contextlib import asynccontextmanager
from datetime import date

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from app.admin_orders import get_admin_order, list_orders
from app.admin_dashboard import get_dashboard_summary
from app.admin_auth import create_admin_session, is_admin_session
from app.customer_api import router as customer_router
from app.partner_api import router as partner_router
from app.catalog import product_menu
from app.config import get_cors_allowed_origins, is_production_environment, validate_production_config
from app.db import SessionLocal
from app.models import OrderModel
from app.delivery_service import (
    add_message_by_delivery,
    assign_delivery_person,
    get_delivery_order_summary,
    list_messages_for_delivery,
    update_delivery_location,
)
from app.menu import MENU
from app.openai_service import generate_admin_reply, generate_reply
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
IS_PRODUCTION = is_production_environment()

from app.mcp_server import build_mcp, enabled as mcp_enabled

customer_mcp, customer_mcp_app = build_mcp() if mcp_enabled() else (None, None)


@asynccontextmanager
async def app_lifespan(application):
    if customer_mcp is not None:
        async with customer_mcp.session_manager.run():
            yield
    else:
        yield

app = FastAPI(
    lifespan=app_lifespan,
    title="Talegaon Fresh AI Agent API",
    description=(
        "Customer ordering, product catalog, order tracking, payment, seller, "
        "inventory, pricing, delivery, and AI assistant APIs for Talegaon Fresh."
    ),
    version="0.9.0",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)
app.state.customer_mcp_transport = customer_mcp_app
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_allowed_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Admin-Token"],
)


def _request_id(request: Request) -> str:
    candidate = request.headers.get("X-Request-ID", "").strip()
    if candidate and len(candidate) <= 64 and all(
        char.isalnum() or char in "._-" for char in candidate
    ):
        request.state.request_id = candidate
        return candidate
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    return request_id


def _apply_security_headers(request: Request, response):
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"
    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/auth/") or request.url.path.startswith("/customers/me"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    return response


@app.middleware("http")
async def security_headers(request: Request, call_next):
    request_id = _request_id(request)
    try:
        rate_limit_response = await enforce_rate_limit(request)
        if rate_limit_response is not None:
            return _apply_security_headers(request, rate_limit_response)
        response = await call_next(request)
    except Exception as exc:
        database_error = isinstance(exc, SQLAlchemyError) or any(
            isinstance(nested, SQLAlchemyError)
            for nested in getattr(exc, "exceptions", ())
        )
        if database_error:
            # SQLAlchemy exception strings may contain SQL parameters (including
            # token hashes). Keep logs useful without emitting query values.
            logger.error(
                "Database operation failed request_id=%s method=%s path=%s error_type=%s",
                request_id,
                request.method,
                request.url.path,
                type(exc).__name__,
            )
            response = JSONResponse(
                status_code=503,
                content={"detail": "Service temporarily unavailable", "request_id": request_id},
            )
        else:
            # Avoid logging arbitrary exception strings in production; providers
            # may include credentials or user data in them.
            if IS_PRODUCTION:
                logger.error(
                    "Unhandled request exception request_id=%s method=%s path=%s error_type=%s",
                    request_id,
                    request.method,
                    request.url.path,
                    type(exc).__name__,
                )
            else:
                logger.exception(
                    "Unhandled request exception request_id=%s method=%s path=%s",
                    request_id,
                    request.method,
                    request.url.path,
                )
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "request_id": request_id},
            )
    return _apply_security_headers(request, response)


app.include_router(customer_router)
app.include_router(partner_router)
if customer_mcp_app is not None:
    app.mount("/mcp", customer_mcp_app)
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET")
validate_production_config()


@app.get("/health")
def health() -> dict:
    return {"service": "Talegaon Fresh AI Agent", "status": "running"}


@app.get("/")
def root() -> dict:
    return health()


@app.get("/privacy-policy", response_class=HTMLResponse)
def privacy_policy_page():
    return HTMLResponse("""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Privacy Policy | FRESHORA</title>
<style>body{font-family:Arial,sans-serif;line-height:1.65;color:#1f2937;max-width:900px;margin:auto;padding:32px 20px}h1,h2{color:#166534}a{color:#166534}</style></head>
<body><h1>Privacy Policy</h1><p><strong>Last updated: October 3, 2026</strong></p>
<p>FRESHORA is a grocery ordering service operated under the Talegaon Fresh brand.</p>
<h2>Information we collect</h2><p>We collect your name, mobile number, delivery addresses, order details, customer-support or AI messages, and information needed to authenticate and secure your account. If you grant location access, we may use approximate location to help identify your delivery area.</p>
<h2>How we use information</h2><p>We use this information to create your account, process and deliver orders, show order status, provide support, prevent abuse, and operate the service.</p>
<h2>Third-party processing</h2><p>AI assistant messages may be processed by our backend and AI infrastructure providers. Cloud hosting and database providers process information needed to operate the service. We do not sell customer personal information.</p>
<h2>Retention and deletion</h2><p>Use the <a href="/delete-account">account deletion page</a> to delete your account and personal data. Transaction records may be retained in anonymized form when required for legal, accounting, fraud-prevention or dispute-resolution purposes.</p>
<h2>Security</h2><p>We use HTTPS, secure session storage, one-way PIN hashing, access controls and rate limiting. No internet service can guarantee absolute security.</p>
<h2>Contact</h2><p>For privacy requests, contact Talegaon Fresh via <a href="https://wa.me/918788543135">WhatsApp at +91 87885 43135</a>.</p>
</body></html>""")


@app.get("/delete-account", response_class=HTMLResponse)
def delete_account_page():
    return HTMLResponse("""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Delete Account | FRESHORA</title>
<style>body{font-family:Arial,sans-serif;line-height:1.65;color:#1f2937;max-width:900px;margin:auto;padding:32px 20px}h1,h2{color:#166534}.box{background:#f0fdf4;border-left:4px solid #166534;padding:16px;margin:20px 0}a{color:#166534}</style></head>
<body><h1>Delete your FRESHORA account</h1>
<p>Sign in to the FRESHORA app, open <strong>Profile</strong>, choose <strong>Delete account</strong>, and confirm.</p>
<div class="box"><strong>Outside the app:</strong> send a WhatsApp request from your registered mobile number to <a href="https://wa.me/918788543135?text=Please%20delete%20my%20FRESHORA%20account%20and%20associated%20personal%20data.">+91 87885 43135</a>.</div>
<p>We delete account, address, active-session, authentication, saved-cart and assistant-state data. Order records may be retained in anonymized form where required for legal, accounting, fraud-prevention or dispute-resolution purposes.</p>
<p>Read the <a href="/privacy-policy">Privacy Policy</a>.</p>
</body></html>""")


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



class AdminSessionRequest(BaseModel):
    admin_token: str = Field(min_length=1, max_length=500)


@app.post("/admin/session")
def admin_session(payload: AdminSessionRequest) -> dict:
    return {
        "access_token": create_admin_session(payload.admin_token),
        "expires_in": 3600,
        "token_type": "bearer",
    }


class PriceUpdateRequest(BaseModel):
    price: float = Field(gt=0)
    in_stock: bool | None = None
    image_url: str | None = Field(default=None, max_length=500)


class CreateProductRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    unit: str = Field(min_length=1, max_length=30)
    category: str = Field(default="Other", min_length=1, max_length=50)
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
    """Accept the legacy admin token and the short-lived admin session."""
    configured = os.getenv("ADMIN_API_TOKEN")
    legacy_token = request.headers.get("X-Admin-Token", "")
    if configured and hmac.compare_digest(legacy_token, configured):
        return True

    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    return scheme.lower() == "bearer" and is_admin_session(token.strip())


@app.get("/admin/dashboard")
async def admin_dashboard(
    request: Request,
    start_date: date | None = None,
    end_date: date | None = None,
):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    try:
        return get_dashboard_summary(start_date=start_date, end_date=end_date)
    except ValueError as exc:
        return PlainTextResponse(str(exc), status_code=400)


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
            name=payload.name,
            unit=payload.unit,
            price=payload.price,
            stock_quantity=payload.stock_quantity,
            image_url=payload.image_url,
            category=payload.category,
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


class AssignDeliveryBatchRequest(BaseModel):
    order_ids: list[int] = Field(min_length=2, max_length=3)
    delivery_person_name: str = Field(min_length=1, max_length=100)
    delivery_person_phone: str = Field(min_length=7, max_length=30)
    distance_km: float = Field(default=0, ge=0, le=100)
    incentive_amount: float = Field(default=0, ge=0, le=10000)


@app.patch("/admin/orders/{order_id}/delivery")
async def admin_assign_delivery(order_id: int, payload: AssignDeliveryRequest, request: Request):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    order = get_admin_order(order_id)
    if not order:
        return PlainTextResponse("Order not found", status_code=404)
    locked_statuses = {"OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"}
    if str(order.get("status", "")).upper() in locked_statuses:
        return PlainTextResponse("Delivery assignment is locked for this order status", status_code=409)

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


@app.post("/admin/orders/delivery-batch")
async def admin_assign_delivery_batch(payload: AssignDeliveryBatchRequest, request: Request):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    if os.getenv("DELIVERY_MULTI_ORDER_ENABLED", "false").strip().lower() != "true":
        return PlainTextResponse("Multi-order delivery is disabled during partner training", status_code=409)
    try:
        max_batch_orders = max(2, min(int(os.getenv("DELIVERY_MAX_BATCH_ORDERS", "2")), 3))
    except ValueError:
        max_batch_orders = 2
    if len(payload.order_ids) > max_batch_orders:
        return PlainTextResponse(f"Batch size cannot exceed {max_batch_orders} orders", status_code=400)
    if len(set(payload.order_ids)) != len(payload.order_ids):
        return PlainTextResponse("Each order ID must be unique", status_code=400)

    orders = []
    for order_id in payload.order_ids:
        order = get_admin_order(order_id)
        if not order:
            return PlainTextResponse(f"Order {order_id} not found", status_code=404)
        if str(order.get("status", "")).upper() in {"OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"}:
            return PlainTextResponse(f"Order {order_id} cannot be assigned in its current status", status_code=409)
        orders.append(order)

    batch_id = f"batch-{uuid.uuid4().hex[:16]}"
    results = []
    for sequence, order in enumerate(orders, start=1):
        result = assign_delivery_person(order["order_id"], payload.delivery_person_name, payload.delivery_person_phone)
        if not result:
            return PlainTextResponse(f"Order {order['order_id']} could not be assigned", status_code=409)
        db = SessionLocal()
        try:
            row = db.get(OrderModel, order["order_id"])
            row.delivery_batch_id = batch_id
            row.delivery_sequence = sequence
            row.delivery_distance_km = payload.distance_km
            row.delivery_incentive = payload.incentive_amount
            db.commit()
        finally:
            db.close()
        result.pop("delivery_token", None)
        results.append({**result, "batch_id": batch_id, "batch_sequence": sequence})

    return {
        "batch_id": batch_id,
        "order_count": len(results),
        "max_orders": max_batch_orders,
        "orders": results,
    }


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

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));
}

async function loadOrder() {
  const res = await fetch(`${base}/delivery/${token}/summary`);
  if (!res.ok) { document.getElementById('order-card').innerText = 'Invalid or expired link.'; return; }
  const data = await res.json();
  let itemsHtml = data.items.map(i => `<li>${escapeHtml(i.quantity)} x ${escapeHtml(i.name)}</li>`).join('');
  document.getElementById('order-card').innerHTML =
    `<b>Order #${escapeHtml(data.order_id)}</b> — ${escapeHtml(data.status)}<br>` +
    `Address: ${escapeHtml(data.address || 'N/A')}<br>Total: Rs.${escapeHtml(data.total)}<br>Payment: ${escapeHtml(data.payment_method || 'N/A')}` +
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
    `<div class="bubble ${m.sender === 'delivery' ? 'delivery' : 'customer'}">${escapeHtml(m.message)}</div>`
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


@app.get("/admin/product-requests")
async def admin_product_requests(request: Request, limit: int = 100):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)
    from app.db import SessionLocal
    from app.models import ProductRequestModel

    db = SessionLocal()
    try:
        safe_limit = max(1, min(limit, 200))
        rows = (
            db.query(ProductRequestModel)
            .order_by(ProductRequestModel.created_at.desc())
            .limit(safe_limit)
            .all()
        )
        return {
            "requests": [
                {
                    "id": row.id,
                    "customer_id": row.customer_id,
                    "order_id": row.order_id,
                    "request_text": row.request_text,
                    "status": row.status,
                    "created_at": row.created_at,
                }
                for row in rows
            ]
        }
    finally:
        db.close()


class AdminAiRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


@app.post("/admin/ai/copilot")
async def admin_ai_copilot(payload: AdminAiRequest, request: Request):
    if not _admin_authorized(request):
        return PlainTextResponse("Unauthorized", status_code=401)

    dashboard = get_dashboard_summary()
    orders = list_orders(limit=50)
    inventory = list_inventory()
    snapshot = {
        "dashboard": dashboard,
        "orders": [
            {
                "order_id": item.get("order_id"),
                "status": item.get("status"),
                "total": item.get("total"),
                "payment_method": item.get("payment_method"),
                "item_count": len(item.get("items") or []),
            }
            for item in orders
        ],
        "inventory": inventory,
    }
    try:
        reply = generate_admin_reply(payload.question, snapshot)
    except Exception:
        logger.exception("Admin Copilot failed")
        return PlainTextResponse("Admin Copilot is temporarily unavailable.", status_code=503)
    return {"reply": reply}


# Campaign editing is restricted to authenticated store administrators.
from app.campaigns import BannerInput, PromotionInput, is_active
from app.models import CampaignBannerModel, PromotionModel


def _campaign_dict(item, fields):
    return {"id": item.id, **{field: getattr(item, field) for field in fields}}


_PROMOTION_FIELDS = ("code", "discount_type", "discount_value", "min_order", "max_discount",
                     "first_order_only", "active", "starts_at", "ends_at")
_BANNER_FIELDS = ("title", "description", "image_url", "promo_code", "display_order",
                  "active", "starts_at", "ends_at")


@app.get("/admin/promotions")
def admin_list_promotions(request: Request):
    if not _admin_authorized(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    with SessionLocal() as db:
        return {"promotions": [_campaign_dict(p, _PROMOTION_FIELDS) for p in db.query(PromotionModel).order_by(PromotionModel.id).all()]}


@app.post("/admin/promotions")
def admin_create_promotion(request: Request, payload: PromotionInput):
    if not _admin_authorized(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    with SessionLocal() as db:
        item = PromotionModel(**payload.model_dump())
        db.add(item)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Promo code already exists")
        db.refresh(item)
        return _campaign_dict(item, _PROMOTION_FIELDS)


@app.put("/admin/promotions/{promotion_id}")
def admin_update_promotion(promotion_id: int, request: Request, payload: PromotionInput):
    if not _admin_authorized(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    with SessionLocal() as db:
        item = db.get(PromotionModel, promotion_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Promotion not found")
        for key, value in payload.model_dump().items():
            setattr(item, key, value)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Promo code already exists")
        db.refresh(item)
        return _campaign_dict(item, _PROMOTION_FIELDS)


@app.get("/admin/banners")
def admin_list_banners(request: Request):
    if not _admin_authorized(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    with SessionLocal() as db:
        return {"banners": [_campaign_dict(b, _BANNER_FIELDS) for b in db.query(CampaignBannerModel).order_by(CampaignBannerModel.display_order, CampaignBannerModel.id).all()]}


@app.post("/admin/banners")
def admin_create_banner(request: Request, payload: BannerInput):
    if not _admin_authorized(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    with SessionLocal() as db:
        item = CampaignBannerModel(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        return _campaign_dict(item, _BANNER_FIELDS)


@app.put("/admin/banners/{banner_id}")
def admin_update_banner(banner_id: int, request: Request, payload: BannerInput):
    if not _admin_authorized(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    with SessionLocal() as db:
        item = db.get(CampaignBannerModel, banner_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Banner not found")
        for key, value in payload.model_dump().items():
            setattr(item, key, value)
        db.commit()
        db.refresh(item)
        return _campaign_dict(item, _BANNER_FIELDS)


@app.get("/campaigns")
def public_campaigns():
    with SessionLocal() as db:
        promotions = db.query(PromotionModel).all()
        active_codes = {p.code for p in promotions if is_active(p)}
        # Built-in codes remain usable unless an administrator creates an override.
        for code in ("FRESH10", "SHOP200", "WELCOME50", "FRESHORA20"):
            if not any(p.code == code for p in promotions):
                active_codes.add(code)
        banners = db.query(CampaignBannerModel).order_by(CampaignBannerModel.display_order, CampaignBannerModel.id).all()
        return {"banners": [_campaign_dict(b, _BANNER_FIELDS) for b in banners
                            if is_active(b) and (not b.promo_code or b.promo_code in active_codes)]}
