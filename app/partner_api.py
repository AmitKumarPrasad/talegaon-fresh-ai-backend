import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.db import SessionLocal
from app.admin_auth import is_admin_session
from app.models import (
    CustomerModel,
    OrderStatusHistoryModel,
    DeliveryPartnerModel,
    DeliveryPartnerSessionModel,
    DeliveryPayoutLedgerModel,
    OrderItemModel,
    OrderModel,
)
from app.order_status import ALLOWED_TRANSITIONS
from app.phone_utils import is_valid_indian_mobile
from app.pin_auth import _pin_hash, _pin_matches
from app.openai_service import generate_partner_reply
from app.notification_service import NotificationService

router = APIRouter(prefix="/partner", tags=["delivery-partner"])
logger = logging.getLogger(__name__)


def _delivery_otp_hash(otp: str) -> str:
    secret = os.getenv("JWT_SECRET", "development-jwt-secret-change-me")
    return hashlib.sha256(f"{secret}:{otp}".encode()).hexdigest()

ACCESS_TOKEN_MINUTES = 30
REFRESH_TOKEN_DAYS = 30
DELIVERY_STATUSES = {"ASSIGNED", "ACCEPTED", "PICKED_UP", "OUT_FOR_DELIVERY", "DELIVERED"}
DELIVERY_TRANSITIONS = {
    "ASSIGNED": {"ACCEPTED"},
    "ACCEPTED": {"PICKED_UP"},
    "PICKED_UP": {"OUT_FOR_DELIVERY"},
    "OUT_FOR_DELIVERY": {"DELIVERED"},
    "DELIVERED": set(),
}


class PartnerAuthRequest(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    pin: str = Field(min_length=6, max_length=6)
    device_id: str = Field(min_length=16, max_length=200)

    @field_validator("phone", "pin", "device_id", mode="before")
    @classmethod
    def _coerce_strings(cls, value: object) -> object:
        return str(value) if isinstance(value, int) else value


class PartnerRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=500)
    device_id: str = Field(min_length=16, max_length=200)


class PartnerLogoutRequest(BaseModel):
    device_id: str = Field(min_length=16, max_length=200)


class PartnerFcmTokenRequest(BaseModel):
    fcm_token: str = Field(min_length=20, max_length=500)


class PartnerProvisionRequest(BaseModel):
    phone: str = Field(min_length=7, max_length=30)
    name: str = Field(min_length=1, max_length=100)
    pin: str = Field(min_length=6, max_length=6)

    @field_validator("phone", "pin", mode="before")
    @classmethod
    def _coerce_strings(cls, value: object) -> object:
        return str(value) if isinstance(value, int) else value


class PartnerStatusRequest(BaseModel):
    status: str = Field(min_length=1, max_length=30)


def _secret() -> str:
    return os.getenv("JWT_SECRET", "development-jwt-secret-change-me")


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _ub64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _credential_version(partner: DeliveryPartnerModel) -> str:
    return hashlib.sha256(partner.pin_hash.encode()).hexdigest()


def _token(partner: DeliveryPartnerModel, session_id: int) -> str:
    now = datetime.now(timezone.utc)
    header = _b64(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64(json.dumps({
        "sub": partner.phone,
        "sid": session_id,
        "name": partner.name,
        "role": "DELIVERY_PARTNER",
        "credential_version": _credential_version(partner),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ACCESS_TOKEN_MINUTES)).timestamp()),
    }, separators=(",", ":")).encode())
    signing = f"{header}.{payload}".encode()
    signature = hmac.new(_secret().encode(), signing, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64(signature)}"


def _decode(token: str) -> dict:
    try:
        header, payload, signature = token.split(".")
        expected = hmac.new(
            _secret().encode(), f"{header}.{payload}".encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, _ub64(signature)):
            raise ValueError
        data = json.loads(_ub64(payload))
        if data.get("role") != "DELIVERY_PARTNER":
            raise ValueError
        if int(data["exp"]) <= int(datetime.now(timezone.utc).timestamp()):
            raise ValueError
        return data
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid or expired partner token")


def _refresh_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _issue(db, partner: DeliveryPartnerModel, device_id: str) -> dict:
    refresh = secrets.token_urlsafe(48)
    session = DeliveryPartnerSessionModel(
        partner_phone=partner.phone,
        device_id=device_id,
        refresh_token_hash=_refresh_hash(refresh),
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS),
    )
    db.add(session)
    db.flush()
    return {
        "access_token": _token(partner, session.id),
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_MINUTES * 60,
        "partner": {"phone": partner.phone, "name": partner.name},
    }


def _active_partner_session(db, data: dict) -> DeliveryPartnerSessionModel:
    session_id = data.get("sid")
    if type(session_id) is not int or session_id <= 0:
        # Legacy access JWTs must refresh once to acquire a revocable session binding.
        raise HTTPException(status_code=401, detail="Partner session must be refreshed")
    session = db.get(DeliveryPartnerSessionModel, session_id)
    if not session or session.partner_phone != data.get("sub") or session.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Partner session revoked. Sign in again.")
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Partner session expired. Sign in again.")
    return session


def current_partner(authorization: str | None = Header(default=None)) -> DeliveryPartnerModel:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Partner authentication required")
    data = _decode(authorization.split(" ", 1)[1].strip())
    db = SessionLocal()
    try:
        partner = db.get(DeliveryPartnerModel, data["sub"])
        if not partner or not partner.active:
            raise HTTPException(status_code=401, detail="Partner account is inactive")
        version = data.get("credential_version")
        if not isinstance(version, str) or not hmac.compare_digest(version, _credential_version(partner)):
            raise HTTPException(status_code=401, detail="Partner session revoked. Sign in again.")
        _active_partner_session(db, data)
        return partner
    finally:
        db.close()


@router.post("/auth/login")
def partner_login(payload: PartnerAuthRequest):
    if not is_valid_indian_mobile(payload.phone.strip()):
        raise HTTPException(status_code=400, detail="Enter a valid 10-digit Indian mobile number")
    db = SessionLocal()
    try:
        partner = db.get(DeliveryPartnerModel, payload.phone.strip())
        if not partner or not partner.active or not _pin_matches(payload.pin, partner.pin_hash):
            raise HTTPException(status_code=401, detail="Invalid partner phone or PIN")
        result = _issue(db, partner, payload.device_id)
        db.commit()
        return result
    finally:
        db.close()


@router.post("/auth/refresh")
def partner_refresh(payload: PartnerRefreshRequest):
    db = SessionLocal()
    try:
        row = db.query(DeliveryPartnerSessionModel).filter(
            DeliveryPartnerSessionModel.refresh_token_hash == _refresh_hash(payload.refresh_token),
            DeliveryPartnerSessionModel.revoked_at.is_(None),
        ).with_for_update().first()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid refresh session")
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= datetime.now(timezone.utc) or row.device_id != payload.device_id:
            raise HTTPException(status_code=401, detail="Refresh session expired or device mismatch")
        partner = db.get(DeliveryPartnerModel, row.partner_phone)
        if not partner or not partner.active:
            raise HTTPException(status_code=401, detail="Partner account is inactive")
        row.revoked_at = datetime.now(timezone.utc)
        result = _issue(db, partner, payload.device_id)
        db.commit()
        return result
    finally:
        db.close()


@router.post("/auth/logout")
def partner_logout(
    payload: PartnerLogoutRequest,
    authorization: str | None = Header(default=None),
):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Partner authentication required")
    data = _decode(authorization.split(" ", 1)[1].strip())
    current_partner(authorization)
    db = SessionLocal()
    try:
        session = _active_partner_session(db, data)
        if session.device_id != payload.device_id:
            raise HTTPException(status_code=401, detail="Logout device mismatch")
        sessions = db.query(DeliveryPartnerSessionModel).filter(
            DeliveryPartnerSessionModel.partner_phone == data["sub"],
            DeliveryPartnerSessionModel.device_id == payload.device_id,
            DeliveryPartnerSessionModel.revoked_at.is_(None),
        ).with_for_update().all()
        revoked_at = datetime.now(timezone.utc)
        for session in sessions:
            session.revoked_at = revoked_at
        db.commit()
        return {"revoked_sessions": len(sessions)}
    finally:
        db.close()




@router.get("/me")
def partner_me(partner: DeliveryPartnerModel = Depends(current_partner)):
    return {"phone": partner.phone, "name": partner.name, "active": partner.active}


@router.put("/me/fcm-token")
def update_partner_fcm_token(payload: PartnerFcmTokenRequest, partner: DeliveryPartnerModel = Depends(current_partner)):
    """Store or update the partner's FCM token for push notifications."""
    db = SessionLocal()
    try:
        partner_obj = db.get(DeliveryPartnerModel, partner.phone)
        if not partner_obj:
            raise HTTPException(status_code=404, detail="Partner not found")
        partner_obj.fcm_token = payload.fcm_token
        db.commit()
        return {"status": "updated"}
    finally:
        db.close()


def _order_dict(db, order: OrderModel) -> dict:
    items = db.query(OrderItemModel).filter(OrderItemModel.order_id == order.id).order_by(OrderItemModel.id.asc()).all()
    return {
        "order_id": order.id,
        "status": order.status,
        "delivery_status": ("CANCELLED" if order.status == "CANCELLED" else order.delivery_status),
        "address": order.address,
        "total": order.total,
        "payment_method": order.payment_method,
        "cod_amount": order.total if order.payment_method == "COD" else 0,
        "batch_id": order.delivery_batch_id or f"order-{order.id}",
        "batch_sequence": order.delivery_sequence or 1,
        "distance_km": round(max(order.delivery_distance_km or 0, 0), 2),
        "items": [
            {"name": item.product_name, "quantity": item.quantity, "unit_price": item.unit_price}
            for item in items
        ],
    }


@router.get("/orders")
def partner_orders(partner: DeliveryPartnerModel = Depends(current_partner)):
    db = SessionLocal()
    try:
        orders = (
            db.query(OrderModel)
            .filter(OrderModel.delivery_person_phone == partner.phone)
            .order_by(OrderModel.id.desc())
            .all()
        )
        return {"orders": [_order_dict(db, order) for order in orders]}
    finally:
        db.close()


@router.get("/orders/{order_id}")
def partner_order(order_id: int, partner: DeliveryPartnerModel = Depends(current_partner)):
    db = SessionLocal()
    try:
        order = db.get(OrderModel, order_id)
        if not order or order.delivery_person_phone != partner.phone:
            raise HTTPException(status_code=404, detail="Assigned order not found")
        return _order_dict(db, order)
    finally:
        db.close()


class PartnerLocationRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


@router.post("/orders/{order_id}/location")
def partner_update_location(
    order_id: int,
    payload: PartnerLocationRequest,
    partner: DeliveryPartnerModel = Depends(current_partner),
):
    db = SessionLocal()
    try:
        order = db.get(OrderModel, order_id)
        if not order or order.delivery_person_phone != partner.phone:
            raise HTTPException(status_code=404, detail="Assigned order not found")
        if order.status == "CANCELLED":
            raise HTTPException(status_code=409, detail="Order was cancelled by the customer")
        if order.status != "OUT_FOR_DELIVERY" or order.delivery_status != "OUT_FOR_DELIVERY":
            raise HTTPException(status_code=409, detail="Location updates are available only while out for delivery")
        order.delivery_lat = payload.lat
        order.delivery_lng = payload.lng
        order.delivery_location_updated_at = datetime.now(timezone.utc)
        db.commit()
        return {"order_id": order_id, "lat": order.delivery_lat, "lng": order.delivery_lng, "updated_at": order.delivery_location_updated_at.isoformat()}
    finally:
        db.close()


def _transition_delivery_order(db, order: OrderModel, new_status: str) -> bool:
    """Stage the order transition in the same transaction as delivery and payout.

    The conditional write also makes concurrent attempts compete for one transition.
    A failed ledger insert or commit rolls back the status and history together.
    """
    previous_status = order.status
    if new_status not in ALLOWED_TRANSITIONS.get(previous_status, set()):
        return False
    updated = db.query(OrderModel).filter(
        OrderModel.id == order.id,
        OrderModel.status == previous_status,
        OrderModel.delivery_status == order.delivery_status,
        OrderModel.delivery_person_phone == order.delivery_person_phone,
    ).update({OrderModel.status: new_status}, synchronize_session=False)
    if updated != 1:
        return False
    order.status = new_status
    db.add(OrderStatusHistoryModel(
        order_id=order.id, from_status=previous_status, to_status=new_status,
    ))
    return True


def _notify_delivery_transition(db, order: OrderModel) -> None:
    # Push failures must never undo a successfully committed delivery/payout.
    try:
        customer = db.get(CustomerModel, order.customer_id)
        if customer and customer.fcm_token:
            NotificationService.notify_customer_order_status(
                customer.fcm_token, order.id, order.status,
            )
    except Exception:
        logger.exception("Order status push failed order_id=%s", order.id)


@router.patch("/orders/{order_id}/status")
def partner_update_status(
    order_id: int,
    payload: PartnerStatusRequest,
    partner: DeliveryPartnerModel = Depends(current_partner),
):
    requested = payload.status.upper()
    if requested not in DELIVERY_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid delivery status")
    db = SessionLocal()
    try:
        order = db.query(OrderModel).filter(OrderModel.id == order_id).with_for_update().first()
        if not order or order.delivery_person_phone != partner.phone:
            raise HTTPException(status_code=404, detail="Assigned order not found")
        if order.status == "CANCELLED":
            raise HTTPException(status_code=409, detail="Order was cancelled by the customer")
        current = (order.delivery_status or "ASSIGNED").upper()
        if requested not in DELIVERY_TRANSITIONS.get(current, set()):
            raise HTTPException(status_code=409, detail=f"Invalid delivery transition from {current} to {requested}")
        if requested == "PICKED_UP" and order.status != "PACKING":
            raise HTTPException(
                status_code=409,
                detail="Store is still packing this order. Ask the store to mark it as PACKING before pickup.",
            )
        if requested == "OUT_FOR_DELIVERY":
            if order.status != "PACKING":
                raise HTTPException(
                    status_code=409,
                    detail="The store has not marked this order as PACKING. Refresh and contact the store before starting delivery.",
                )
            if not _transition_delivery_order(db, order, "OUT_FOR_DELIVERY"):
                raise HTTPException(status_code=409, detail="Order status cannot move to OUT_FOR_DELIVERY")
        if requested == "DELIVERED":
            raise HTTPException(
                status_code=400,
                detail="Use /complete with the customer delivery OTP and COD confirmation",
            )
        order.delivery_status = requested
        db.commit()
        if requested == "OUT_FOR_DELIVERY":
            _notify_delivery_transition(db, order)
        return _order_dict(db, order)
    finally:
        db.close()


class DeliveryCompletionRequest(BaseModel):
    otp: str = Field(min_length=6, max_length=6)
    cod_collected: bool = False


@router.post("/orders/{order_id}/complete")
def partner_complete_delivery(
    order_id: int,
    payload: DeliveryCompletionRequest,
    partner: DeliveryPartnerModel = Depends(current_partner),
):
    db = SessionLocal()
    try:
        order = db.query(OrderModel).filter(OrderModel.id == order_id).with_for_update().first()
        if not order or order.delivery_person_phone != partner.phone:
            raise HTTPException(status_code=404, detail="Assigned order not found")
        if order.status == "CANCELLED":
            raise HTTPException(status_code=409, detail="Order was cancelled by the customer")
        if order.delivery_status != "OUT_FOR_DELIVERY" or order.status != "OUT_FOR_DELIVERY":
            raise HTTPException(status_code=409, detail="Order is not out for delivery")
        if order.payment_method == "COD" and not payload.cod_collected:
            raise HTTPException(status_code=409, detail="Confirm COD collection before completion")
        expires = order.delivery_otp_expires_at
        if not order.delivery_otp_hash or not expires:
            raise HTTPException(status_code=409, detail="Customer must generate a delivery OTP first")
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Delivery OTP expired")
        if order.delivery_otp_attempts >= 5:
            raise HTTPException(status_code=429, detail="Too many invalid delivery OTP attempts")
        if not hmac.compare_digest(order.delivery_otp_hash, _delivery_otp_hash(payload.otp)):
            order.delivery_otp_attempts += 1
            db.commit()
            # 401 is reserved for partner session authentication. Clients retry
            # it after refreshing, which would count one wrong OTP twice.
            raise HTTPException(status_code=400, detail="Invalid delivery OTP")
        if not _transition_delivery_order(db, order, "DELIVERED"):
            raise HTTPException(status_code=409, detail="Order status cannot move to DELIVERED")
        order.delivery_status = "DELIVERED"
        order.delivery_otp_hash = None
        order.delivery_otp_expires_at = None
        order.delivery_otp_attempts = 0
        # Create the payout record only after the delivery is verified and delivered.
        # Amounts are backend-controlled; partners cannot edit payout or COD values.
        if not db.query(DeliveryPayoutLedgerModel).filter(
            DeliveryPayoutLedgerModel.order_id == order.id
        ).first():
            base_amount = max(float(os.getenv("DELIVERY_BASE_RATE", "25")), 0)
            per_km_rate = max(float(os.getenv("DELIVERY_PER_KM_RATE", "8")), 0)
            included_km = max(float(os.getenv("DELIVERY_INCLUDED_KM", "1")), 0)
            distance_km = max(float(order.delivery_distance_km or 0), 0)
            batch_count = 1
            if order.delivery_batch_id:
                batch_count = max(
                    db.query(OrderModel)
                    .filter(OrderModel.delivery_batch_id == order.delivery_batch_id)
                    .count(),
                    1,
                )
            # Distance and batch incentive are entered once for the route and split
            # across its stops; the base amount remains payable per delivered order.
            distance_amount = max(distance_km - included_km, 0) * per_km_rate / batch_count
            incentive_amount = max(float(order.delivery_incentive or 0), 0) / batch_count
            payout_amount = base_amount + distance_amount + incentive_amount
            db.add(DeliveryPayoutLedgerModel(
                order_id=order.id,
                partner_phone=partner.phone,
                payout_amount=round(payout_amount, 2),
                base_amount=round(base_amount, 2),
                distance_km=round(distance_km, 2),
                distance_amount=round(distance_amount, 2),
                incentive_amount=round(incentive_amount, 2),
                cod_amount=order.total if order.payment_method == "COD" else 0,
                status="PENDING",
            ))
        db.commit()
        _notify_delivery_transition(db, order)
        return _order_dict(db, order)
    finally:
        db.close()


@router.get("/earnings")
def partner_earnings(partner: DeliveryPartnerModel = Depends(current_partner)):
    db = SessionLocal()
    try:
        entries = (
            db.query(DeliveryPayoutLedgerModel)
            .filter(DeliveryPayoutLedgerModel.partner_phone == partner.phone)
            .order_by(DeliveryPayoutLedgerModel.created_at.desc())
            .all()
        )
        earned = sum(entry.payout_amount for entry in entries)
        pending = sum(entry.payout_amount for entry in entries if entry.status == "PENDING")
        paid = sum(entry.payout_amount for entry in entries if entry.status == "PAID")
        cod = sum(entry.cod_amount for entry in entries)
        base_rate = max(float(os.getenv("DELIVERY_BASE_RATE", "25")), 0)
        per_km_rate = max(float(os.getenv("DELIVERY_PER_KM_RATE", "8")), 0)
        included_km = max(float(os.getenv("DELIVERY_INCLUDED_KM", "1")), 0)
        return {
            "currency": "INR",
            "completed_orders": len(entries),
            "base_rate": base_rate,
            "per_km_rate": per_km_rate,
            "included_km": included_km,
            "distance_amount": sum(entry.distance_amount for entry in entries),
            "incentive_amount": sum(entry.incentive_amount for entry in entries),
            "earned_amount": earned,
            "estimated_earnings": earned,
            "pending_payout": pending,
            "paid_amount": paid,
            "cod_reconciliation_amount": cod,
            "payout_schedule": "WEEKLY",
            "tips": 0,
            "status": "LEDGER",
            "entries": [
                {
                    "order_id": entry.order_id,
                    "payout_amount": entry.payout_amount,
                    "base_amount": entry.base_amount,
                    "distance_km": entry.distance_km,
                    "distance_amount": entry.distance_amount,
                    "incentive_amount": entry.incentive_amount,
                    "cod_amount": entry.cod_amount,
                    "status": entry.status,
                    "created_at": entry.created_at.isoformat(),
                    "paid_at": entry.paid_at.isoformat() if entry.paid_at else None,
                }
                for entry in entries
            ],
        }
    finally:
        db.close()


def _settle_payout_entry(entry: DeliveryPayoutLedgerModel) -> bool:
    if entry.status == "PAID":
        return False
    if entry.status != "PENDING":
        raise ValueError("Only pending payouts can be marked paid")
    entry.status = "PAID"
    entry.paid_at = datetime.now(timezone.utc)
    return True


def _admin_authorized(request: Request) -> bool:
    configured = os.getenv("ADMIN_API_TOKEN")
    if configured and hmac.compare_digest(request.headers.get("X-Admin-Token", ""), configured):
        return True
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return is_admin_session(authorization.split(" ", 1)[1].strip())
    return False


@router.get("/admin/payouts")
def admin_payouts(
    request: Request,
    status: str | None = None,
    partner_phone: str | None = None,
):
    if not _admin_authorized(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    normalized_status = status.upper() if status else None
    if normalized_status and normalized_status not in {"PENDING", "PAID"}:
        raise HTTPException(status_code=400, detail="Status must be PENDING or PAID")
    db = SessionLocal()
    try:
        query = db.query(DeliveryPayoutLedgerModel)
        if normalized_status:
            query = query.filter(DeliveryPayoutLedgerModel.status == normalized_status)
        if partner_phone:
            query = query.filter(DeliveryPayoutLedgerModel.partner_phone == partner_phone.strip())
        entries = query.order_by(DeliveryPayoutLedgerModel.created_at.desc()).all()
        return {
            "currency": "INR",
            "payout_schedule": "WEEKLY",
            "total_payout": sum(entry.payout_amount for entry in entries),
            "pending_payout": sum(entry.payout_amount for entry in entries if entry.status == "PENDING"),
            "paid_payout": sum(entry.payout_amount for entry in entries if entry.status == "PAID"),
            "cod_reconciliation_amount": sum(entry.cod_amount for entry in entries),
            "entries": [
                {
                    "id": entry.id,
                    "order_id": entry.order_id,
                    "partner_phone": entry.partner_phone,
                    "payout_amount": entry.payout_amount,
                    "base_amount": entry.base_amount,
                    "distance_km": entry.distance_km,
                    "distance_amount": entry.distance_amount,
                    "incentive_amount": entry.incentive_amount,
                    "cod_amount": entry.cod_amount,
                    "status": entry.status,
                    "created_at": entry.created_at.isoformat(),
                    "paid_at": entry.paid_at.isoformat() if entry.paid_at else None,
                }
                for entry in entries
            ],
        }
    finally:
        db.close()



@router.post("/admin/payouts/{ledger_id}/mark-paid")
def mark_partner_payout_paid(ledger_id: int, request: Request):
    if not _admin_authorized(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    db = SessionLocal()
    try:
        entry = db.get(DeliveryPayoutLedgerModel, ledger_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Payout ledger entry not found")
        try:
            _settle_payout_entry(entry)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error))
        db.commit()
        return {
            "id": entry.id,
            "order_id": entry.order_id,
            "partner_phone": entry.partner_phone,
            "payout_amount": entry.payout_amount,
            "cod_amount": entry.cod_amount,
            "status": entry.status,
            "paid_at": entry.paid_at.isoformat() if entry.paid_at else None,
        }
    finally:
        db.close()


@router.post("/admin/partners")
def provision_partner(payload: PartnerProvisionRequest, request: Request):
    if not _admin_authorized(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not is_valid_indian_mobile(payload.phone.strip()):
        raise HTTPException(status_code=400, detail="Enter a valid 10-digit Indian mobile number")
    db = SessionLocal()
    try:
        partner = db.get(DeliveryPartnerModel, payload.phone.strip())
        if partner:
            partner.name = payload.name.strip()
            partner.pin_hash = _pin_hash(payload.pin)
            db.query(DeliveryPartnerSessionModel).filter(
                DeliveryPartnerSessionModel.partner_phone == partner.phone,
                DeliveryPartnerSessionModel.revoked_at.is_(None),
            ).update({"revoked_at": datetime.now(timezone.utc)}, synchronize_session=False)
            partner.active = True
        else:
            partner = DeliveryPartnerModel(
                phone=payload.phone.strip(),
                name=payload.name.strip(),
                pin_hash=_pin_hash(payload.pin),
                active=True,
            )
            db.add(partner)
        db.commit()
        return {"phone": partner.phone, "name": partner.name, "active": partner.active}
    finally:
        db.close()


@router.get("/admin/partners")
def list_admin_partners(request: Request):
    if not _admin_authorized(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    db = SessionLocal()
    try:
        partners = db.query(DeliveryPartnerModel).order_by(DeliveryPartnerModel.created_at.desc()).all()
        return {"partners": [{"phone": item.phone, "name": item.name, "active": item.active, "created_at": item.created_at.isoformat()} for item in partners]}
    finally:
        db.close()


class PartnerActiveRequest(BaseModel):
    active: bool


@router.patch("/admin/partners/{phone}")
def update_partner_active(phone: str, payload: PartnerActiveRequest, request: Request):
    if not _admin_authorized(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    db = SessionLocal()
    try:
        partner = db.get(DeliveryPartnerModel, phone.strip())
        if not partner:
            raise HTTPException(status_code=404, detail="Partner not found")
        partner.active = payload.active
        db.commit()
        return {"phone": partner.phone, "name": partner.name, "active": partner.active}
    finally:
        db.close()


class PartnerAiRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


@router.post("/ai/assistant")
def partner_ai_assistant(
    payload: PartnerAiRequest,
    partner: DeliveryPartnerModel = Depends(current_partner),
):
    db = SessionLocal()
    try:
        orders = (
            db.query(OrderModel)
            .filter(OrderModel.delivery_person_phone == partner.phone)
            .order_by(OrderModel.id.desc())
            .limit(20)
            .all()
        )
        entries = (
            db.query(DeliveryPayoutLedgerModel)
            .filter(DeliveryPayoutLedgerModel.partner_phone == partner.phone)
            .order_by(DeliveryPayoutLedgerModel.created_at.desc())
            .limit(100)
            .all()
        )
        earned = sum(entry.payout_amount for entry in entries)
        pending = sum(entry.payout_amount for entry in entries if entry.status == "PENDING")
        paid = sum(entry.payout_amount for entry in entries if entry.status == "PAID")
        cod = sum(entry.cod_amount for entry in entries)
        snapshot = {
            "partner_name": partner.name,
            "deliveries": [
                {
                    "order_id": order.id,
                    "status": order.status,
                    "delivery_status": order.delivery_status,
                    "address": order.address,
                    "total": order.total,
                    "payment_method": order.payment_method,
                }
                for order in orders
            ],
            "earnings": {
                "currency": "INR",
                "earned_amount": earned,
                "pending_payout": pending,
                "paid_amount": paid,
                "cod_reconciliation_amount": cod,
                "payout_schedule": "WEEKLY",
                "entries": [
                    {
                        "order_id": entry.order_id,
                        "payout_amount": entry.payout_amount,
                        "cod_amount": entry.cod_amount,
                        "status": entry.status,
                        "created_at": entry.created_at.isoformat(),
                    }
                    for entry in entries
                ],
            },
        }
    finally:
        db.close()

    try:
        reply = generate_partner_reply(payload.question, snapshot)
    except Exception:
        raise HTTPException(status_code=503, detail="Delivery Partner Assistant is temporarily unavailable")
    return {"reply": reply}


