from datetime import datetime, timezone
import re

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field, field_validator
import os

from app.auth import current_customer, logout_customer
from app.pin_auth import register as register_pin, login as login_pin, refresh as refresh_pin, revoke as revoke_refresh
from app.db import SessionLocal
from app.models import AddressModel, CustomerModel, OrderItemModel, OrderModel, ProductModel
from app.order_details import get_customer_order, save_payment_link
from app.payment_service import PaymentError, create_payment_link
from app.order_status import get_allowed_transitions
from app.delivery_service import add_message_by_customer, get_tracking_info, list_messages_for_customer
from app.seller_notification import notify_seller

router = APIRouter()


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


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=500)
    device_id: str = Field(min_length=16, max_length=200)


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
    pincode: str = Field(min_length=6, max_length=6)
    is_default: bool = False


class CartItem(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    unit: str = Field(min_length=1, max_length=30)
    price: float = Field(ge=0)
    quantity: int = Field(ge=1)


class CartRequest(BaseModel):
    items: list[CartItem] = Field(default_factory=list)


class OrderRequest(BaseModel):
    items: list[CartItem] = Field(min_length=1)
    address_id: int | None = None
    address: str | None = Field(default=None, max_length=500)
    payment_method: str | None = Field(default=None, max_length=20)


class AiChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


def _mobile_ai_reply(message: str, customer_id: str) -> str:
    """Return authoritative order answers before falling back to the LLM."""
    normalized = message.strip().lower()
    match = re.search(r"\\b(?:order\\s*(?:id|number|no|#)?\\s*)?(\\d{1,10})\\b", normalized)
    asks_status = any(term in normalized for term in ("order status", "tracking", "track my", "where is my order", "status of my order"))
    asks_order_number = any(term in normalized for term in ("order number", "order id", "my order no", "my order number")) and not match

    db = SessionLocal()
    try:
        order = None
        if match and (asks_status or "order" in normalized):
            order_id = int(match.group(1))
            candidate = db.get(OrderModel, order_id)
            if candidate and candidate.customer_id == customer_id:
                order = candidate
        if order is None and (asks_status or asks_order_number):
            order = (
                db.query(OrderModel)
                .filter(OrderModel.customer_id == customer_id)
                .order_by(OrderModel.id.desc())
                .first()
            )
        if order is not None and (asks_status or asks_order_number):
            return (
                f"📦 Your latest order is Order #{order.id}.\\n"
                f"Status: {order.status.replace('_', ' ').title()}\\n"
                f"Total: ₹{order.total:.2f}\\n"
                f"Payment: {order.payment_method or 'Not selected'}\\n"
                f"Delivery: {order.address or 'Not provided'}"
            )
        if match and asks_status:
            return "I couldn't find that order under your account. Please check the Order ID shown in My Orders."
    finally:
        db.close()

    from app.openai_service import generate_mobile_reply
    return generate_mobile_reply(message)


def _address_dict(item: AddressModel) -> dict:
    return {"id": item.id, "label": item.label, "address": item.address, "city": item.city, "pincode": item.pincode, "is_default": item.is_default}


def _order_dict(db, order: OrderModel) -> dict:
    items = db.query(OrderItemModel).filter(OrderItemModel.order_id == order.id).all()
    return {
        "order_id": order.id,
        "status": order.status,
        "allowed_next_statuses": sorted(get_allowed_transitions(order.status)),
        "total": order.total,
        "address": order.address,
        "payment_method": order.payment_method,
        "payment_link_url": order.payment_link_url,
        "created_at": order.created_at.isoformat(),
        "items": [
            {"name": i.product_name, "quantity": i.quantity, "unit_price": i.unit_price, "line_total": i.line_total}
            for i in items
        ],
    }


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


@router.get("/customers/me")
def get_me(customer: CustomerModel = Depends(current_customer)):
    return {"phone": customer.phone, "name": customer.name}


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
def mobile_ai_chat(
    payload: AiChatRequest,
    customer: CustomerModel = Depends(current_customer),
):
    try:
        reply = _mobile_ai_reply(payload.message, customer.phone)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="AI service is temporarily unavailable.") from exc
    return {"reply": reply}


@router.post("/customers/me/orders")
def create_order(payload: OrderRequest, customer: CustomerModel = Depends(current_customer)):
    db = SessionLocal()
    try:
        address = payload.address
        if payload.address_id is not None:
            saved = db.get(AddressModel, payload.address_id)
            if not saved or saved.customer_id != customer.phone:
                raise HTTPException(status_code=404, detail="Address not found")
            address = f"{saved.address}, {saved.city}, {saved.pincode}"
        if not address:
            raise HTTPException(status_code=400, detail="Delivery address is required")
        order = OrderModel(customer_id=customer.phone, address=address, status="PENDING")
        db.add(order)
        db.flush()
        total = 0.0
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
            product = db.get(ProductModel, product.id)
            product.in_stock = product.stock_quantity > 0
            line_total = round(product.price * item.quantity, 2)
            db.add(OrderItemModel(order_id=order.id, product_name=product.name, quantity=item.quantity, unit_price=product.price, line_total=line_total))
            total += line_total
        order.total = round(total, 2)
        order.stock_reserved = True
        if payload.payment_method:
            method = payload.payment_method.upper()
            if method not in {"UPI", "COD"}:
                raise HTTPException(status_code=400, detail="Invalid payment method")
            order.payment_method = method
            order.status = "PAYMENT_PENDING" if method == "UPI" else "CONFIRMED"
        db.commit()
        db.refresh(order)
        response = _order_dict(db, order)
        try:
            notify_seller(
                order_id=order.id,
                customer_id=customer.phone,
                total=order.total,
                address=order.address,
                payment_method=order.payment_method or "PAYMENT_PENDING",
            )
        except Exception:
            # Customer checkout must not fail because seller notification is unavailable.
            import logging
            logging.getLogger(__name__).exception(
                "Order created but seller notification failed order_id=%s", order.id
            )
        return response
    finally:
        db.close()



@router.post("/customers/me/orders/{order_id}/payment-link")
def create_customer_payment_link(
    order_id: int,
    customer: CustomerModel = Depends(current_customer),
):
    order = get_customer_order(order_id, customer.phone)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["payment_method"] != "UPI":
        raise HTTPException(status_code=400, detail="Order payment method must be UPI")
    if order["status"] != "PAYMENT_PENDING":
        raise HTTPException(status_code=409, detail="Order is not awaiting UPI payment")
    if order.get("payment_link_url"):
        return {
            "order_id": order_id,
            "status": order["status"],
            "payment_link_url": order["payment_link_url"],
        }
    try:
        link = create_payment_link(order_id, order["total"], customer.phone)
        if not save_payment_link(order_id, link["id"], link["short_url"]):
            raise PaymentError("Order could not be updated with the payment link")
    except PaymentError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "order_id": order_id,
        "status": "PAYMENT_PENDING",
        "payment_link_url": link["short_url"],
    }

@router.get("/customers/me/orders/{order_id}")
def get_customer_order_details(order_id: int, customer: CustomerModel = Depends(current_customer)):
    order = get_customer_order(order_id, customer.phone)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get("/customers/me/orders")
def list_customer_orders(customer: CustomerModel = Depends(current_customer)):
    db = SessionLocal()
    try:
        orders = db.query(OrderModel).filter(OrderModel.customer_id == customer.phone).order_by(OrderModel.id.desc()).all()
        return {"orders": [_order_dict(db, order) for order in orders]}
    finally:
        db.close()


@router.get("/customers/me/orders/{order_id}/tracking")
def get_order_tracking(order_id: int, customer: CustomerModel = Depends(current_customer)):
    tracking = get_tracking_info(order_id, customer.phone)
    if not tracking:
        raise HTTPException(status_code=404, detail="Order not found")
    return tracking


@router.get("/customers/me/orders/{order_id}/messages")
def list_order_messages(order_id: int, customer: CustomerModel = Depends(current_customer)):
    messages = list_messages_for_customer(order_id, customer.phone)
    if messages is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"messages": messages}


@router.post("/customers/me/orders/{order_id}/messages")
def send_order_message(order_id: int, payload: OrderMessageRequest, customer: CustomerModel = Depends(current_customer)):
    message = add_message_by_customer(order_id, customer.phone, payload.message)
    if message is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return message

