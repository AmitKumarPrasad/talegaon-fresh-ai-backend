from datetime import datetime, timedelta, timezone
import json
import hashlib
import secrets
import re

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
import os

from app.auth import current_customer, logout_customer
from app.pin_auth import (
    CustomerSessionModel,
    PinCredentialModel,
    register as register_pin,
    login as login_pin,
    refresh as refresh_pin,
    revoke as revoke_refresh,
)
from app.db import SessionLocal
from app.models import (
    AddressModel,
    CheckoutRequestModel,
    ConversationStateModel,
    CustomerModel,
    OrderItemModel,
    OrderMessageModel,
    OrderModel,
    OrderStatusHistoryModel,
    ProductModel,
    ProductRequestModel,
    DeliveryPartnerModel,
)
from app.campaigns import is_active
from app.models import PromotionModel
from app.order_details import customer_order_dict as _order_dict, get_customer_order
from app.payment_service import PaymentError, cancel_payment_link, create_payment_link
from app.order_status import get_allowed_transitions, list_status_history
from app.delivery_service import add_message_by_customer, get_tracking_info, list_messages_for_customer
from app.seller_notification import notify_seller
from app.notification_service import NotificationService
from app.state import get_state
from app.phone_utils import is_valid_indian_mobile

from app import reviewer

router = APIRouter()


def _delivery_otp_hash(otp: str) -> str:
    secret = os.getenv("JWT_SECRET", "development-jwt-secret-change-me")
    return hashlib.sha256(f"{secret}:{otp}".encode()).hexdigest()


class OrderMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class PinAuthRequest(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    pin: str = Field(min_length=6, max_length=6)
    device_id: str = Field(min_length=16, max_length=200)
    name: str | None = Field(default=None, max_length=100)

    @field_validator("phone", "pin", "device_id", mode="before")
    @classmethod
    def _coerce_pin_fields(cls, value: object) -> object:
        return str(value) if isinstance(value, int) else value

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        value = value.strip()
        if not is_valid_indian_mobile(value):
            raise ValueError("Enter a valid 10-digit Indian mobile number")
        return value


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=500)
    device_id: str = Field(min_length=16, max_length=200)


class FcmTokenRequest(BaseModel):
    fcm_token: str = Field(min_length=20, max_length=500)


class OtpRequest(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    name: str | None = Field(default=None, max_length=100)

    @field_validator("phone", mode="before")
    @classmethod
    def _coerce_phone(cls, value: object) -> object:
        return str(value) if isinstance(value, int) else value


class OtpVerify(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    otp: str = Field(min_length=4, max_length=8)
    name: str | None = Field(default=None, max_length=100)

    @field_validator("phone", "otp", mode="before")
    @classmethod
    def _coerce_str(cls, value: object) -> object:
        return str(value) if isinstance(value, int) else value


class AddressRequest(BaseModel):
    label: str = Field(min_length=1, max_length=50)
    address: str = Field(min_length=1, max_length=500)
    city: str = Field(min_length=1, max_length=100)
    pincode: str = Field(pattern=r"^[1-9][0-9]{5}$")
    is_default: bool = False


class CartItem(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    unit: str = Field(min_length=1, max_length=30)
    price: float = Field(ge=0)
    quantity: int = Field(ge=1, le=100)


class CartRequest(BaseModel):
    items: list[CartItem] = Field(default_factory=list, max_length=50)


class OrderRequest(BaseModel):
    idempotency_key: str | None = Field(default=None, min_length=16, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    items: list[CartItem] = Field(min_length=1, max_length=50)
    address_id: int | None = None
    address: str | None = Field(default=None, max_length=500)
    payment_method: str | None = Field(default=None, max_length=20)
    promo_code: str | None = Field(default=None, max_length=32)


class PromoValidationRequest(BaseModel):
    items: list[CartItem] = Field(min_length=1, max_length=50)
    promo_code: str = Field(min_length=1, max_length=32)


class AiChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


_PROMO_RULES = {
    "FRESH10": {"percent": 0.10, "max_discount": 50.0, "min_order": 0.0},
    "SHOP200": {"flat_discount": 20.0, "min_order": 200.0},
    "WELCOME50": {"flat_discount": 50.0, "min_order": 499.0, "first_order_only": True},
    "FRESHORA20": {"percent": 0.20, "max_discount": 100.0, "min_order": 499.0},
}
_DELIVERY_THRESHOLD = 199.0
_DELIVERY_FEE = 20.0


def _promo_rule(db, customer_id: str, promo_code: str | None) -> tuple[str, dict] | None:
    if not promo_code or not promo_code.strip():
        return None

    code = promo_code.strip().upper()
    configured = db.query(PromotionModel).filter(PromotionModel.code == code).first()
    if configured is not None:
        if not is_active(configured):
            raise HTTPException(status_code=400, detail="This promo code is not active.")
        rule = {"min_order": configured.min_order, "first_order_only": configured.first_order_only}
        if configured.discount_type == "flat":
            rule["flat_discount"] = configured.discount_value
        else:
            rule["percent"] = configured.discount_value / 100
            rule["max_discount"] = configured.max_discount
    else:
        rule = _PROMO_RULES.get(code)
    if rule is not None:
        if rule.get("first_order_only") and db.query(OrderModel.id).filter(
            OrderModel.customer_id == customer_id
        ).first():
            raise HTTPException(
                status_code=400,
                detail="This promo code is only valid on your first order.",
            )
        return code, rule

    referrer = db.query(CustomerModel).filter(
        CustomerModel.referral_code == code
    ).first()
    if not referrer or referrer.phone == customer_id:
        raise HTTPException(status_code=400, detail="Invalid promo code.")

    prior_order = db.query(OrderModel.id).filter(
        OrderModel.customer_id == customer_id
    ).first()
    if prior_order:
        raise HTTPException(
            status_code=400,
            detail="Referral codes are only valid on your first order.",
        )

    return code, {
        "percent": 0.20,
        "max_discount": 100.0,
        "min_order": 499.0,
    }


def _discount_amount(rule: dict | None, subtotal: float) -> float:
    if rule is None:
        return 0.0
    minimum = rule["min_order"]
    if subtotal < minimum:
        raise HTTPException(
            status_code=400,
            detail=f"This code requires a product subtotal of ₹{minimum:.0f}.",
        )
    if "flat_discount" in rule:
        return min(round(rule["flat_discount"], 2), subtotal)
    return min(
        round(subtotal * rule["percent"], 2),
        rule["max_discount"],
        subtotal,
    )


def _quote_order(db, customer_id: str, items: list[CartItem], promo_code: str) -> dict:
    resolved_promo = _promo_rule(db, customer_id, promo_code)
    subtotal = 0.0
    for item in items:
        product = db.query(ProductModel).filter(
            ProductModel.name.ilike(item.name)
        ).first()
        if not product:
            raise HTTPException(status_code=400, detail=f"Product not found: {item.name}")
        subtotal += round(product.price * item.quantity, 2)
    subtotal = round(subtotal, 2)
    delivery_fee = _DELIVERY_FEE if subtotal < _DELIVERY_THRESHOLD else 0.0
    discount = _discount_amount(
        resolved_promo[1] if resolved_promo else None,
        subtotal,
    )
    return {
        "promo_code": resolved_promo[0] if resolved_promo else None,
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "discount_amount": discount,
        "total": round(subtotal + delivery_fee - discount, 2),
    }


def _catalog_reply(message: str) -> str | None:
    """Answer product/price/stock questions from the live catalog."""
    normalized = re.sub(r"[^a-z0-9 ]+", " ", message.strip().lower())
    asks_catalog = any(
        term in normalized
        for term in (
            "price", "cost", "how much", "available", "in stock",
            "products", "product list", "what can i buy", "what do you sell",
        )
    )
    if not asks_catalog:
        return None

    db = SessionLocal()
    try:
        products = db.query(ProductModel).order_by(ProductModel.id).all()
        if not products:
            return "Please open the Products screen to see the current catalog."

        stop_words = {
            "what", "are", "is", "the", "price", "cost", "of", "for", "how",
            "much", "does", "do", "you", "have", "any", "available", "in",
            "stock", "products", "product", "list", "can", "i", "buy", "show",
            "me", "please", "tell", "about", "today", "your",
        }
        tokens = {token for token in normalized.split() if len(token) >= 3 and token not in stop_words}
        matches = [
            product for product in products
            if not tokens or any(
                token in product.name.lower() or product.name.lower() in token
                for token in tokens
            )
        ]
        if not matches and tokens:
            return "I couldn't find that item. Please check the Products screen for the live catalog."
        if not tokens:
            matches = products[:8]

        lines = []
        for product in matches[:8]:
            availability = "In stock" if product.in_stock else "Out of stock"
            lines.append(f"• {product.name} ({product.unit}) — ₹{product.price:.2f} · {availability}")
        prefix = "Here are the live catalog details:" if tokens else "Here are some products currently listed:"
        return prefix + "\n" + "\n".join(lines) + "\n\nPrices and stock can change; the Products screen is authoritative."
    finally:
        db.close()


def _mobile_ai_reply(message: str, customer_id: str) -> str:
    """Return authoritative order answers before falling back to the LLM."""
    normalized = message.strip().lower().rstrip("?!. ")
    order_match = re.search(
        r"\b(?:order\s*(?:id|number|no|#)?\s*)?(\d{1,10})\b",
        normalized,
    )
    asks_status = any(
        term in normalized
        for term in (
            "order status",
            "tracking",
            "track my",
            "track order",
            "where is my order",
            "status of my order",
            "status of order",
            "my order status",
            "check my order",
            "check order",
            "track my order",
        )
    )
    asks_order_number = any(
        term in normalized
        for term in (
            "order number",
            "order id",
            "my order no",
            "my order number",
            "what is my order",
            "what is my latest order",
            "show my latest order",
            "latest order number",
            "show my order",
            "show my orders",
            "my orders",
            "order details",
        )
    )
    tracking_without_order = asks_status and order_match is None and any(
        term in normalized
        for term in (
            "tracking",
            "track order",
            "track my order",
            "where is my order",
        )
    )
    state = get_state(customer_id)
    awaiting_order_id = state.status_order_lookup
    is_order_id_reply = awaiting_order_id and normalized.isdigit() and order_match is not None
    asks_specific_order = (
        order_match is not None
        and ("order" in normalized or asks_status or is_order_id_reply)
    )

    catalog_reply = _catalog_reply(message)
    if catalog_reply is not None:
        return catalog_reply

    basic_intents = {
        "hi", "hello", "hey", "hii", "good morning", "good afternoon",
        "good evening", "help", "what can you do", "how can you help"
    }
    if normalized in basic_intents:
        return (
            "Hi! 👋 I can help with your FRESHORA orders. "
            "You can ask for your latest order, order status, tracking, or order details."
        )

    if tracking_without_order:
        state.status_order_lookup = True
        return (
            "Sure — I can check the tracking for you. "
            "Please share the Order ID shown in My Orders."
        )

    if is_order_id_reply:
        asks_status = True

    db = SessionLocal()
    try:
        order = None
        if asks_specific_order:
            order_id = int(order_match.group(1))
            candidate = db.get(OrderModel, order_id)
            if candidate and candidate.customer_id == customer_id:
                order = candidate

        if order is None and (asks_status or asks_order_number) and not asks_specific_order and not is_order_id_reply:
            order = (
                db.query(OrderModel)
                .filter(OrderModel.customer_id == customer_id)
                .order_by(OrderModel.id.desc())
                .first()
            )

        if order is not None and (asks_status or asks_order_number):
            status = order.status.replace("_", " ").title()
            tracking = get_tracking_info(order.id, customer_id) if asks_status else None
            reply = (
                f"📦 Order #{order.id}\n"
                f"Status: {status}\n"
                f"Total: ₹{order.total:.2f}\n"
                f"Payment: {order.payment_method or 'Not selected'}"
            )
            if order.address:
                reply += f"\nDelivery: {order.address}"
            if tracking and tracking.get("delivery_person_name"):
                reply += f"\nDelivery partner: {tracking['delivery_person_name']}"
            if tracking and tracking.get("delivery_location_updated_at"):
                reply += f"\nLive location updated: {tracking['delivery_location_updated_at']}"
            if awaiting_order_id:
                state.status_order_lookup = False
            return reply

        if order_match and asks_status:
            if awaiting_order_id:
                state.status_order_lookup = False
            return (
                "I couldn't find that order under your account. "
                "Please check the Order ID shown in My Orders."
            )

        if asks_status or asks_order_number:
            return (
                "I couldn't find any orders under your account yet. "
                "Please place an order first, or share the Order ID from My Orders."
            )
    finally:
        db.close()

    from app.openai_service import generate_mobile_reply
    return generate_mobile_reply(message)


def _address_dict(item: AddressModel) -> dict:
    return {"id": item.id, "label": item.label, "address": item.address, "city": item.city, "pincode": item.pincode, "is_default": item.is_default}


LEGACY_CHECKOUT_RETRY_WINDOW = timedelta(minutes=2)


def _legacy_checkout_retry_is_recent(response: dict) -> bool:
    created_at = response.get("created_at")
    if not created_at:
        return False
    try:
        created_at = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - created_at.astimezone(timezone.utc)
    return timedelta(0) <= age <= LEGACY_CHECKOUT_RETRY_WINDOW


@router.post("/auth/register")
def auth_register(payload: PinAuthRequest):
    return register_pin(payload.phone, payload.name or "Customer", payload.pin, payload.device_id)


@router.post("/auth/login")
def auth_login(payload: PinAuthRequest):
    return login_pin(payload.phone, payload.pin, payload.device_id)


@router.post("/auth/refresh")
def auth_refresh(payload: RefreshRequest):
    return refresh_pin(payload.refresh_token, payload.device_id)


@router.post("/auth/logout-session")
def auth_logout_session(payload: RefreshRequest):
    revoke_refresh(payload.refresh_token)
    return {"status": "logged_out"}


@router.post("/auth/logout")
def auth_logout(customer: CustomerModel = Depends(current_customer)):
    logout_customer(customer)
    return {"status": "logged_out"}


@router.put("/customers/me/fcm-token")
def update_fcm_token(payload: FcmTokenRequest, customer: CustomerModel = Depends(current_customer)):
    """Store or update the customer's FCM token for push notifications."""
    db = SessionLocal()
    try:
        customer_obj = db.get(CustomerModel, customer.phone)
        if not customer_obj:
            raise HTTPException(status_code=404, detail="Customer not found")
        customer_obj.fcm_token = payload.fcm_token
        db.commit()
        return {"status": "updated"}
    finally:
        db.close()

@router.delete("/customers/me")
def delete_customer_account(customer: CustomerModel = Depends(current_customer)):
    """Delete account data and anonymize retained transaction records."""
    db = SessionLocal()
    try:
        orders = db.query(OrderModel).filter(OrderModel.customer_id == customer.phone).all()
        order_ids = [order.id for order in orders]
        if order_ids:
            db.query(OrderMessageModel).filter(OrderMessageModel.order_id.in_(order_ids)).delete(synchronize_session=False)
            db.query(OrderItemModel).filter(OrderItemModel.order_id.in_(order_ids)).delete(synchronize_session=False)
            db.query(OrderStatusHistoryModel).filter(OrderStatusHistoryModel.order_id.in_(order_ids)).delete(synchronize_session=False)
            for order in orders:
                order.customer_id = "deleted"
                order.address = None
                order.delivery_person_name = None
                order.delivery_person_phone = None
                order.delivery_token = None
                order.delivery_token_expires_at = None
                order.delivery_lat = None
                order.delivery_lng = None
                order.delivery_location_updated_at = None

        db.query(reviewer.ReviewerOrderModel).filter_by(customer_id=customer.phone).delete(synchronize_session=False)
        db.query(AddressModel).filter(AddressModel.customer_id == customer.phone).delete(synchronize_session=False)
        db.query(CustomerSessionModel).filter(CustomerSessionModel.customer_id == customer.phone).delete(synchronize_session=False)
        db.query(PinCredentialModel).filter(PinCredentialModel.customer_id == customer.phone).delete(synchronize_session=False)
        db.query(ConversationStateModel).filter(ConversationStateModel.customer_id == customer.phone).delete(synchronize_session=False)
        db.delete(customer)
        db.commit()
        return {"status": "deleted"}
    finally:
        db.close()


@router.get("/customers/me")
def get_me(customer: CustomerModel = Depends(current_customer)):
    return {"phone": customer.phone, "name": customer.name, "is_reviewer": reviewer.is_reviewer(customer.phone)}


@router.get("/customers/me/addresses")
def list_addresses(customer: CustomerModel = Depends(current_customer)):
    db = SessionLocal()
    try:
        rows = db.query(AddressModel).filter(AddressModel.customer_id == customer.phone).order_by(AddressModel.is_default.desc(), AddressModel.id.asc()).all()
        return {"addresses": [_address_dict(row) for row in rows]}
    finally:
        db.close()


@router.post("/customers/me/addresses")
def create_address(payload: AddressRequest, customer: CustomerModel = Depends(current_customer)):
    db = SessionLocal()
    try:
        if payload.is_default:
            db.query(AddressModel).filter(AddressModel.customer_id == customer.phone).update({"is_default": False})
        row = AddressModel(customer_id=customer.phone, **payload.model_dump())
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"address": _address_dict(row)}
    finally:
        db.close()


@router.put("/customers/me/addresses/{address_id}")
def update_address_api(address_id: int, payload: AddressRequest, customer: CustomerModel = Depends(current_customer)):
    db = SessionLocal()
    try:
        row = db.get(AddressModel, address_id)
        if not row or row.customer_id != customer.phone:
            raise HTTPException(status_code=404, detail="Address not found")
        if payload.is_default:
            db.query(AddressModel).filter(AddressModel.customer_id == customer.phone).update({"is_default": False})
        for key, value in payload.model_dump().items():
            setattr(row, key, value)
        db.commit()
        db.refresh(row)
        return {"address": _address_dict(row)}
    finally:
        db.close()


@router.delete("/customers/me/addresses/{address_id}")
def delete_address(address_id: int, customer: CustomerModel = Depends(current_customer)):
    db = SessionLocal()
    try:
        row = db.get(AddressModel, address_id)
        if not row or row.customer_id != customer.phone:
            raise HTTPException(status_code=404, detail="Address not found")
        db.delete(row)
        db.commit()
        return {"status": "deleted"}
    finally:
        db.close()


def _cart_response(db, customer: CustomerModel) -> dict:
    return {"items": customer.cart or []}


@router.get("/customers/me/cart")
def get_cart(customer: CustomerModel = Depends(current_customer)):
    db = SessionLocal()
    try:
        row = db.get(CustomerModel, customer.phone)
        return _cart_response(db, row)
    finally:
        db.close()


@router.put("/customers/me/cart")
def replace_cart(payload: CartRequest, customer: CustomerModel = Depends(current_customer)):
    db = SessionLocal()
    try:
        row = db.get(CustomerModel, customer.phone)
        row.cart = [item.model_dump() for item in payload.items]
        db.commit()
        db.refresh(row)
        return _cart_response(db, row)
    finally:
        db.close()


@router.delete("/customers/me/cart")
def clear_cart(customer: CustomerModel = Depends(current_customer)):
    db = SessionLocal()
    try:
        row = db.get(CustomerModel, customer.phone)
        row.cart = []
        db.commit()
        return {"status": "cleared"}
    finally:
        db.close()


@router.post("/customers/me/ai/chat")
async def mobile_ai_chat(
    payload: AiChatRequest,
    request: Request,
    customer: CustomerModel = Depends(current_customer),
):
    if reviewer.is_reviewer(customer.phone):
        catalog = _catalog_reply(payload.message)
        if catalog:
            return {"reply": catalog}
        demo_orders = reviewer.list_orders(customer.phone)
        latest = demo_orders[0] if demo_orders else None
        return {"reply": (f"Demo order #{latest['order_id']}: Delivered. Total ₹{latest['total']:.2f}. No payment or real delivery is required." if latest else "Reviewer demo: browse products, add a delivery address anywhere, and place a COD demo order. No real delivery or payment is made.")}
    try:
        transport = getattr(request.app.state, "customer_mcp_transport", None)
        if transport is not None:
            from app.mcp_chat import generate_mcp_reply
            reply = await generate_mcp_reply(
                payload.message, request.headers.get("authorization", ""), transport
            )
        else:
            from starlette.concurrency import run_in_threadpool
            reply = await run_in_threadpool(_mobile_ai_reply, payload.message, customer.phone)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="AI service is temporarily unavailable.") from exc
    return {"reply": reply}


@router.get("/customers/me/referral-code")
def get_customer_referral_code(customer: CustomerModel = Depends(current_customer)):
    db = SessionLocal()
    try:
        stored = (
            db.query(CustomerModel)
            .filter(CustomerModel.phone == customer.phone)
            .with_for_update()
            .first()
        )
        if not stored:
            raise HTTPException(status_code=401, detail="Customer not found")
        if stored.referral_code:
            return {"referral_code": stored.referral_code}

        for _ in range(5):
            stored.referral_code = f"FRESHORA{secrets.token_hex(4).upper()}"
            try:
                db.commit()
                return {"referral_code": stored.referral_code}
            except IntegrityError:
                db.rollback()
                stored = db.get(CustomerModel, customer.phone)
                if stored and stored.referral_code:
                    return {"referral_code": stored.referral_code}
        raise HTTPException(
            status_code=503,
            detail="Could not generate a referral code. Please try again.",
        )
    finally:
        db.close()


@router.post("/customers/me/promos/validate")
def validate_customer_promo(
    payload: PromoValidationRequest,
    customer: CustomerModel = Depends(current_customer),
):
    db = SessionLocal()
    try:
        return _quote_order(db, customer.phone, payload.items, payload.promo_code)
    finally:
        db.close()


@router.post("/customers/me/orders")
def create_order(payload: OrderRequest, customer: CustomerModel = Depends(current_customer)):
    db = SessionLocal()
    try:
        db.query(CustomerModel).filter(
            CustomerModel.phone == customer.phone
        ).with_for_update().first()
        request_hash = hashlib.sha256(json.dumps(payload.model_dump(exclude={"idempotency_key"}), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        checkout_key = payload.idempotency_key
        legacy_checkout = checkout_key is None
        if legacy_checkout:
            # Older installed apps may omit an idempotency key. Reuse their
            # checkout response for a short retry window without changing the
            # current client contract.
            checkout_key = f"legacy-{request_hash}"
        checkout_request = db.get(CheckoutRequestModel, (customer.phone, checkout_key))
        if checkout_request:
            if legacy_checkout:
                if _legacy_checkout_retry_is_recent(checkout_request.response):
                    return checkout_request.response
            else:
                if checkout_request.request_hash != request_hash:
                    raise HTTPException(409, "Checkout request changed. Start a new checkout.")
                return checkout_request.response
        address = payload.address
        if payload.address_id is not None:
            saved = db.get(AddressModel, payload.address_id)
            if not saved or saved.customer_id != customer.phone:
                raise HTTPException(status_code=404, detail="Address not found")
            address = f"{saved.address}, {saved.city}, {saved.pincode}"
        if not address:
            raise HTTPException(status_code=400, detail="Delivery address is required")
        reviewer.require_service_area(address, customer.phone)
        if reviewer.is_reviewer(customer.phone):
            if payload.payment_method and payload.payment_method.upper() != "COD":
                raise HTTPException(400, "Reviewer orders use simulated COD only")
            quote = _quote_order(db, customer.phone, payload.items, payload.promo_code or "")
            response = reviewer.create_order(db, customer, payload, address, quote, commit=False)
            if checkout_key:
                if checkout_request:
                    checkout_request.request_hash = request_hash
                    checkout_request.response = response
                else:
                    db.add(CheckoutRequestModel(customer_id=customer.phone, request_key=checkout_key, request_hash=request_hash, response=response))
            db.commit()
            return response
        promo_code = payload.promo_code.strip().upper() if payload.promo_code else None
        resolved_promo = _promo_rule(db, customer.phone, promo_code)
        order = OrderModel(
            customer_id=customer.phone,
            address=address,
            status="PENDING",
            promo_code=resolved_promo[0] if resolved_promo else None,
        )
        db.add(order)
        db.flush()
        subtotal = 0.0
        for item in payload.items:
            product = db.query(ProductModel).filter(ProductModel.name.ilike(item.name)).first()
            if not product:
                raise HTTPException(status_code=400, detail=f"Product not found: {item.name}")
            if not product.in_stock or product.stock_quantity < item.quantity:
                raise HTTPException(status_code=409, detail=f"Insufficient stock: {product.name}")
            updated = (
                db.query(ProductModel)
                .filter(
                    ProductModel.id == product.id,
                    ProductModel.stock_quantity >= item.quantity,
                    ProductModel.in_stock.is_(True),
                )
                .update(
                    {ProductModel.stock_quantity: ProductModel.stock_quantity - item.quantity},
                    synchronize_session=False,
                )
            )
            if updated != 1:
                raise HTTPException(status_code=409, detail=f"Insufficient stock: {product.name}")
            db.refresh(product)
            product.in_stock = product.stock_quantity > 0
            line_total = round(product.price * item.quantity, 2)
            db.add(OrderItemModel(order_id=order.id, product_name=product.name, quantity=item.quantity, unit_price=product.price, line_total=line_total))
            subtotal += line_total
        subtotal = round(subtotal, 2)
        order.delivery_fee = _DELIVERY_FEE if subtotal < _DELIVERY_THRESHOLD else 0.0
        order.discount_amount = _discount_amount(
            resolved_promo[1] if resolved_promo else None,
            subtotal,
        )
        order.total = round(
            subtotal + order.delivery_fee - order.discount_amount,
            2,
        )
        order.stock_reserved = True
        if payload.payment_method:
            method = payload.payment_method.upper()
            if method not in {"UPI", "COD"}:
                raise HTTPException(status_code=400, detail="Invalid payment method")
            order.payment_method = method
            next_status = "PAYMENT_PENDING" if method == "UPI" else "CONFIRMED"
            order.status = next_status
            db.add(OrderStatusHistoryModel(
                order_id=order.id,
                from_status="PENDING",
                to_status=next_status,
            ))
        db.flush()
        response = _order_dict(db, order)
        if checkout_key:
            if checkout_request:
                checkout_request.request_hash = request_hash
                checkout_request.response = response
            else:
                db.add(CheckoutRequestModel(customer_id=customer.phone, request_key=checkout_key, request_hash=request_hash, response=response))
        db.commit()
        try:
            notify_seller(
                order_id=order.id,
                customer_id=customer.phone,
                total=order.total,
                address=order.address,
                payment_method=order.payment_method or "PAYMENT_PENDING",
            )
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Order created but seller notification failed order_id=%s", order.id
            )
        
        # Notify delivery partners about the new order
        try:
            partners = db.query(DeliveryPartnerModel).filter(
                DeliveryPartnerModel.active.is_(True),
                DeliveryPartnerModel.fcm_token.isnot(None),
            ).all()
            for partner in partners:
                NotificationService.notify_partner_new_order(
                    partner_fcm_token=partner.fcm_token,
                    order_id=order.id,
                )
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Order created but partner notification failed order_id=%s", order.id
            )
        
        return response
    finally:
        db.close()


@router.post("/customers/me/orders/{order_id}/payment-link")
def create_customer_payment_link(
    order_id: int,
    customer: CustomerModel = Depends(current_customer),
):
    if reviewer.is_reviewer(customer.phone):
        raise HTTPException(400, "No real payments are available for reviewer demo orders")

    snapshot = get_customer_order(order_id, customer.phone)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Order not found")
    if snapshot["payment_method"] != "UPI":
        raise HTTPException(status_code=400, detail="Order payment method must be UPI")
    if snapshot["status"] != "PAYMENT_PENDING":
        raise HTTPException(status_code=409, detail="Order is not awaiting UPI payment")
    if snapshot.get("payment_link_url"):
        return {
            "order_id": order_id,
            "status": snapshot["status"],
            "payment_link_url": snapshot["payment_link_url"],
        }

    db = SessionLocal()
    try:
        # Keep the order locked while creating and persisting the external link.
        # A second request waits here, then sees and reuses the first link rather
        # than issuing another payable Razorpay link for the same order.
        order = (
            db.query(OrderModel)
            .filter(
                OrderModel.id == order_id,
                OrderModel.customer_id == customer.phone,
            )
            .with_for_update()
            .first()
        )
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if order.payment_method != "UPI":
            raise HTTPException(status_code=400, detail="Order payment method must be UPI")
        if order.status != "PAYMENT_PENDING":
            raise HTTPException(status_code=409, detail="Order is not awaiting UPI payment")
        if order.payment_link_url:
            return {
                "order_id": order_id,
                "status": order.status,
                "payment_link_url": order.payment_link_url,
            }

        try:
            link = create_payment_link(order_id, order.total, customer.phone)
            order.razorpay_payment_link_id = link["id"]
            order.payment_link_url = link["short_url"]
            db.commit()
        except PaymentError as exc:
            db.rollback()
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception:
            db.rollback()
            raise

        return {
            "order_id": order_id,
            "status": "PAYMENT_PENDING",
            "payment_link_url": link["short_url"],
        }
    finally:
        db.close()


@router.post("/customers/me/orders/{order_id}/cancel")
def cancel_customer_order(
    order_id: int,
    customer: CustomerModel = Depends(current_customer),
):
    if reviewer.is_reviewer(customer.phone):
        raise HTTPException(status_code=409, detail="Demo orders cannot be cancelled.")
    db = SessionLocal()
    try:
        order = (
            db.query(OrderModel)
            .filter(
                OrderModel.id == order_id,
                OrderModel.customer_id == customer.phone,
            )
            .with_for_update()
            .first()
        )
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        if order.payment_verified_at or order.razorpay_payment_id:
            raise HTTPException(
                status_code=409,
                detail="Payment was received. Please contact support to cancel and arrange a refund.",
            )
        if "CANCELLED" not in get_allowed_transitions(order.status):
            raise HTTPException(
                status_code=409,
                detail="This order can no longer be cancelled from the app. Please contact support.",
            )
        if order.razorpay_payment_link_id:
            try:
                cancel_payment_link(order.razorpay_payment_link_id)
            except PaymentError as exc:
                raise HTTPException(
                    status_code=503,
                    detail="The payment link could not be cancelled. Please retry or contact support.",
                ) from exc
        if order.stock_reserved:
            items = db.query(OrderItemModel).filter(OrderItemModel.order_id == order.id).all()
            for item in items:
                updated = (
                    db.query(ProductModel)
                    .filter(ProductModel.name == item.product_name)
                    .update(
                        {ProductModel.stock_quantity: ProductModel.stock_quantity + int(item.quantity)},
                        synchronize_session=False,
                    )
                )
                if updated != 1:
                    db.rollback()
                    raise HTTPException(status_code=409, detail="Could not release reserved stock. Please contact support.")
                product = db.query(ProductModel).filter(ProductModel.name == item.product_name).first()
                if product:
                    product.in_stock = product.stock_quantity > 0
            order.stock_reserved = False
        previous_status = order.status
        order.status = "CANCELLED"
        db.add(OrderStatusHistoryModel(
            order_id=order.id,
            from_status=previous_status,
            to_status="CANCELLED",
        ))
        db.commit()
        response = _order_dict(db, order)
        stored_customer = db.get(CustomerModel, customer.phone)
        fcm_token = stored_customer.fcm_token if stored_customer else None
        if fcm_token:
            try:
                NotificationService.notify_customer_order_status(fcm_token, order_id, "CANCELLED")
            except Exception:
                import logging
                logging.getLogger(__name__).exception("Order cancellation push failed order_id=%s", order_id)
        return response
    finally:
        db.close()


@router.get("/customers/me/orders/{order_id}")
def get_customer_order_details(order_id: int, customer: CustomerModel = Depends(current_customer)):
    if reviewer.is_reviewer(customer.phone):
        return reviewer.get_order(customer.phone, order_id)
    order = get_customer_order(order_id, customer.phone)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get("/customers/me/orders")
def list_customer_orders(customer: CustomerModel = Depends(current_customer)):
    if reviewer.is_reviewer(customer.phone):
        return {"orders": reviewer.list_orders(customer.phone)}
    db = SessionLocal()
    try:
        orders = db.query(OrderModel).filter(OrderModel.customer_id == customer.phone).order_by(OrderModel.id.desc()).all()
        return {"orders": [_order_dict(db, order) for order in orders]}
    finally:
        db.close()


@router.get("/customers/me/orders/{order_id}/status-history")
def get_order_status_history(order_id: int, customer: CustomerModel = Depends(current_customer)):
    if reviewer.is_reviewer(customer.phone):
        return {"order_id": order_id, "history": reviewer.get_order(customer.phone, order_id)["history"]}
    order = get_customer_order(order_id, customer.phone)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"order_id": order_id, "history": list_status_history(order_id, customer.phone)}


@router.get("/customers/me/orders/{order_id}/tracking")
def get_order_tracking(order_id: int, customer: CustomerModel = Depends(current_customer)):
    if reviewer.is_reviewer(customer.phone):
        return reviewer.get_order(customer.phone, order_id)
    tracking = get_tracking_info(order_id, customer.phone)
    if not tracking:
        raise HTTPException(status_code=404, detail="Order not found")
    return tracking


@router.post("/customers/me/orders/{order_id}/delivery-code")
@router.post("/customers/me/orders/{order_id}/delivery-otp")
def create_delivery_otp(order_id: int, customer: CustomerModel = Depends(current_customer)):
    if reviewer.is_reviewer(customer.phone):
        reviewer.get_order(customer.phone, order_id)
        raise HTTPException(409, "Demo delivery is already complete; no delivery code is required")
    db = SessionLocal()
    try:
        order = db.get(OrderModel, order_id)
        if not order or order.customer_id != customer.phone:
            raise HTTPException(status_code=404, detail="Order not found")
        if order.status != "OUT_FOR_DELIVERY" or order.delivery_status != "OUT_FOR_DELIVERY":
            raise HTTPException(status_code=409, detail="Delivery OTP is available when the order is out for delivery")
        otp = f"{secrets.randbelow(1_000_000):06d}"
        order.delivery_otp_hash = _delivery_otp_hash(otp)
        order.delivery_otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        order.delivery_otp_attempts = 0
        db.commit()
        return {"order_id": order_id, "expires_in_seconds": 900, "delivery_otp": otp}
    finally:
        db.close()


@router.get("/customers/me/orders/{order_id}/messages")
def list_order_messages(order_id: int, customer: CustomerModel = Depends(current_customer)):
    if reviewer.is_reviewer(customer.phone):
        return {"messages": reviewer.get_order(customer.phone, order_id)["messages"]}
    messages = list_messages_for_customer(order_id, customer.phone)
    if messages is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"messages": messages}


@router.post("/customers/me/orders/{order_id}/messages")
def send_order_message(order_id: int, payload: OrderMessageRequest, customer: CustomerModel = Depends(current_customer)):
    if reviewer.is_reviewer(customer.phone):
        return reviewer.append_entry(customer.phone, order_id, "messages", {"sender":"customer", "message":payload.message})
    message = add_message_by_customer(order_id, customer.phone, payload.message)
    if message is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return message


class ProductRequestPayload(BaseModel):
    request_text: str = Field(min_length=2, max_length=1000)


@router.post("/customers/me/orders/{order_id}/product-request")
def submit_product_request(
    order_id: int,
    payload: ProductRequestPayload,
    customer: CustomerModel = Depends(current_customer),
):
    if reviewer.is_reviewer(customer.phone):
        return reviewer.append_entry(customer.phone, order_id, "product_requests", {"order_id":order_id, "request_text":payload.request_text.strip(), "status":"DEMO"})
    order = get_customer_order(order_id, customer.phone)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if str(order.get("status", "")).upper() != "DELIVERED":
        raise HTTPException(status_code=409, detail="Product requests are available after delivery")

    db = SessionLocal()
    try:
        request = ProductRequestModel(
            customer_id=customer.phone,
            order_id=order_id,
            request_text=payload.request_text.strip(),
        )
        db.add(request)
        db.commit()
        db.refresh(request)
        return {
            "id": request.id,
            "order_id": request.order_id,
            "request_text": request.request_text,
            "status": request.status,
            "created_at": request.created_at,
        }
    finally:
        db.close()


