import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException

from app.db import SessionLocal
from app.models import CustomerModel
from app.msg91_service import send_otp, verify_otp as verify_msg91_otp

logger = logging.getLogger(__name__)

OTP_TTL_MINUTES = 5
DEV_OTP = "123456"
OTP_REQUEST_LIMIT = 3
OTP_REQUEST_WINDOW_MINUTES = 10
OTP_MAX_FAILED_ATTEMPTS = 5
OTP_LOCK_MINUTES = 15


def _secret() -> str:
    return os.getenv("JWT_SECRET", "development-jwt-secret-change-me")


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _ub64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_token(phone: str, name: str, auth_version: int = 1) -> str:
    header = _b64(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64(json.dumps({
        "sub": phone,
        "name": name,
        "ver": auth_version,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp()),
    }, separators=(",", ":")).encode())
    signing = f"{header}.{payload}".encode()
    signature = hmac.new(_secret().encode(), signing, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64(signature)}"


def decode_token(token: str) -> dict:
    try:
        header, payload, signature = token.split(".")
        expected = hmac.new(
            _secret().encode(), f"{header}.{payload}".encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, _ub64(signature)):
            raise ValueError
        data = json.loads(_ub64(payload))
        if int(data["exp"]) < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError
        if not data.get("sub"):
            raise ValueError
        return data
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def current_customer(authorization: str | None = Header(default=None)) -> CustomerModel:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    data = decode_token(authorization.split(" ", 1)[1].strip())
    db = SessionLocal()
    try:
        customer = db.get(CustomerModel, data["sub"])
        if not customer:
            raise HTTPException(status_code=401, detail="Customer not found")
        if int(data.get("ver", 0)) != customer.auth_version:
            raise HTTPException(status_code=401, detail="Session revoked")
        # PIN access tokens are bound to the refresh-session row so a
        # device logout immediately invalidates that device's access token.
        from app.pin_auth import CustomerSessionModel, PinCredentialModel

        session_hash = data.get("sid")
        if session_hash is not None:
            if not isinstance(session_hash, str):
                raise HTTPException(status_code=401, detail="Invalid session")
            session = db.query(CustomerSessionModel).filter(
                CustomerSessionModel.refresh_token_hash == session_hash,
                CustomerSessionModel.customer_id == customer.phone,
                CustomerSessionModel.revoked_at.is_(None),
            ).first()
            if not session:
                raise HTTPException(status_code=401, detail="Session revoked")
            expires = session.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= datetime.now(timezone.utc):
                raise HTTPException(status_code=401, detail="Session expired")
        elif db.get(PinCredentialModel, customer.phone) is not None:
            # Existing PIN clients can obtain a bound token using refresh.
            # Never let an older unbound token bypass session revocation.
            raise HTTPException(status_code=401, detail="Refresh session required")
        return customer
    finally:
        db.close()


def request_otp(phone: str, name: str | None = None, reveal_otp: bool = False) -> dict:
    phone = phone.strip()
    if not phone:
        raise HTTPException(status_code=400, detail="Phone is required")
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        customer = db.get(CustomerModel, phone)
        if not customer:
            customer = CustomerModel(phone=phone, name=(name or "").strip() or "Customer")
            db.add(customer)
        elif name and name.strip():
            customer.name = name.strip()

        locked_until = customer.otp_locked_until
        if locked_until and locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until and locked_until > now:
            raise HTTPException(status_code=429, detail="Too many OTP attempts. Try again later.")

        window_started = customer.otp_window_started_at
        if window_started and window_started.tzinfo is None:
            window_started = window_started.replace(tzinfo=timezone.utc)
        if not window_started or window_started + timedelta(minutes=OTP_REQUEST_WINDOW_MINUTES) <= now:
            customer.otp_window_started_at = now
            customer.otp_request_count = 0

        if customer.otp_request_count >= OTP_REQUEST_LIMIT:
            retry_at = customer.otp_window_started_at + timedelta(minutes=OTP_REQUEST_WINDOW_MINUTES)
            retry_seconds = max(1, int((retry_at - now).total_seconds()))
            db.rollback()
            raise HTTPException(status_code=429, detail=f"OTP request limit reached. Retry in {retry_seconds} seconds.")

        is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
        otp = os.getenv("DEV_OTP", DEV_OTP)
        customer.otp_expires_at = now + timedelta(minutes=OTP_TTL_MINUTES)
        customer.otp_request_count += 1
        customer.otp_failed_attempts = 0
        customer.otp_locked_until = None
        try:
            if is_production:
                send_otp(phone)
                customer.otp_hash = hashlib.sha256(b"msg91-provider").hexdigest()
            else:
                customer.otp_hash = hashlib.sha256(otp.encode()).hexdigest()
        except Exception as exc:
            db.rollback()
            logger.exception("Failed to send OTP SMS to %s", phone)
            raise HTTPException(status_code=503, detail="OTP delivery is temporarily unavailable") from exc

        db.commit()
        result = {"message": "OTP requested", "expires_in_seconds": OTP_TTL_MINUTES * 60}
        if not is_production:
            result["demo_otp"] = otp
        if reveal_otp and not is_production:
            result["otp"] = otp
        return result
    finally:
        db.close()


def verify_otp(phone: str, otp: str, name: str | None = None, device_id: str | None = None) -> dict:
    db = SessionLocal()
    try:
        customer = db.get(CustomerModel, phone.strip())
        now = datetime.now(timezone.utc)
        if not customer or not customer.otp_hash or not customer.otp_expires_at:
            raise HTTPException(status_code=401, detail="OTP not requested")

        locked_until = customer.otp_locked_until
        if locked_until and locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until and locked_until > now:
            raise HTTPException(status_code=429, detail="Too many invalid OTP attempts. Try again later.")

        expires = customer.otp_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < now:
            raise HTTPException(status_code=401, detail="OTP expired")

        is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
        if is_production:
            try:
                valid = verify_msg91_otp(phone.strip(), otp)
            except Exception as exc:
                logger.exception("Failed to verify OTP with MSG91 for %s", phone)
                raise HTTPException(status_code=503, detail="OTP verification is temporarily unavailable") from exc
        else:
            valid = hmac.compare_digest(customer.otp_hash, hashlib.sha256(otp.encode()).hexdigest())

        if not valid:
            customer.otp_failed_attempts += 1
            if customer.otp_failed_attempts >= OTP_MAX_FAILED_ATTEMPTS:
                customer.otp_locked_until = now + timedelta(minutes=OTP_LOCK_MINUTES)
                db.commit()
                raise HTTPException(status_code=429, detail="Too many invalid OTP attempts. Try again later.")
            db.commit()
            remaining = OTP_MAX_FAILED_ATTEMPTS - customer.otp_failed_attempts
            raise HTTPException(status_code=401, detail=f"Invalid OTP. {remaining} attempts remaining.")

        if name and name.strip():
            customer.name = name.strip()
        customer.otp_hash = None
        customer.otp_expires_at = None
        customer.otp_failed_attempts = 0
        customer.otp_locked_until = None
        customer.otp_request_count = 0
        customer.otp_window_started_at = None
        # OTP and PIN authentication must issue the same revocable session
        # format, including when an existing PIN customer verifies an OTP.
        from app.pin_auth import _issue

        session_device = device_id or ("verified-otp-" + secrets.token_urlsafe(24))
        if not isinstance(session_device, str) or not 16 <= len(session_device) <= 200:
            raise HTTPException(status_code=400, detail="Invalid session device")
        result = _issue(db, customer, session_device)
        db.commit()
        return {**result, "token": result["access_token"], "device_id": session_device}
    finally:
        db.close()


def logout_customer(customer: CustomerModel) -> None:
    db = SessionLocal()
    try:
        row = db.get(CustomerModel, customer.phone)
        if not row:
            return
        # Refresh tokens must be revoked in the same transaction as access
        # tokens; otherwise an old session can immediately undo logout.
        from app.pin_auth import CustomerSessionModel

        row.auth_version += 1
        # This model stores one active push token per account. Clear it on
        # logout so order updates cannot reach a signed-out device.
        row.fcm_token = None
        db.query(CustomerSessionModel).filter(
            CustomerSessionModel.customer_id == row.phone,
            CustomerSessionModel.revoked_at.is_(None),
        ).update(
            {"revoked_at": datetime.now(timezone.utc)},
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()
