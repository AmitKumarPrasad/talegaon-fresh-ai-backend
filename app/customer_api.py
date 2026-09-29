from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import current_customer, logout_customer, request_otp, verify_otp
from app.db import SessionLocal
from app.models import AddressModel, CustomerModel, OrderItemModel, OrderModel, ProductModel
from app.order_details import get_customer_order
from app.order_status import get_allowed_transitions

router = APIRouter()


class OtpRequest(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    name: str | None = Field(default=None, max_length=100)


class OtpVerify(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    otp: str = Field(min_length=4, max_length=8)
    name: str | None = Field(default=None, max_length=100)


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


def _address_dict(item: AddressModel) -> dict:
    return {"id": item.id, "label": item.label, "address": item.address, "city": item.city, "pincode": item.pincode, "is_default": item.is_default}


def _order_dict(db, order: OrderModel) -> dict:
    items = db.query(OrderItemModel).filter(OrderItemModel.order_id == order.id).all()
    return {
        "order_id": order.id,
        "customer_id": order.customer_id,
        "status": order.status,
        "allowed_next_statuses": sorted(get_allowed_transitions(order.status)),
        "total": order.total,
        "address": order.address,
        "payment_method": order.payment_method,
        "payment_link_url": order.payment_link_url,
        "items": [
            {"name": i.product_name, "quantity": i.quantity, "unit_price": i.unit_price, "line_total": i.line_total}
            for i in items
        ],
    }


@router.post("/auth/request-otp")
def auth_request(payload: OtpRequest):
    return request_otp(payload.phone, payload.name)


@router.post("/auth/verify-otp")
def auth_verify(payload: OtpVerify):
    return verify_otp(payload.phone, payload.otp, payload.name)


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
        return _order_dict(db, order)
    finally:
        db.close()


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
