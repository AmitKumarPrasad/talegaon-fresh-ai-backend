import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException

from app.db import SessionLocal
from app.models import CustomerModel

OTP_TTL_MINUTES = 5
DEV_OTP = "123456"


def _secret() -> str:
    return os.getenv("JWT_SECRET", "development-jwt-secret-change-me")


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _ub64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_token(phone: str, name: str) -> str:
    header = _b64(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64(json.dumps({
        "sub": phone,
        "name": name,
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
        return customer
    finally:
        db.close()


def request_otp(phone: str, name: str | None = None) -> dict:
    phone = phone.strip()
    if not phone:
        raise HTTPException(status_code=400, detail="Phone is required")
    db = SessionLocal()
    try:
        customer = db.get(CustomerModel, phone)
        if not customer:
            customer = CustomerModel(phone=phone, name=(name or "").strip() or "Customer")
            db.add(customer)
        elif name and name.strip():
            customer.name = name.strip()
        otp = os.getenv("DEV_OTP", DEV_OTP)
        if os.getenv("ENVIRONMENT", "development").lower() == "production":
            otp = f"{secrets.randbelow(1_000_000):06d}"
        customer.otp_hash = hashlib.sha256(otp.encode()).hexdigest()
        customer.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES)
        db.commit()
        result = {"message": "OTP requested", "expires_in_seconds": OTP_TTL_MINUTES * 60}
        if os.getenv("ENVIRONMENT", "development").lower() != "production":
            result["demo_otp"] = otp
        return result
    finally:
        db.close()


def verify_otp(phone: str, otp: str, name: str | None = None) -> dict:
    db = SessionLocal()
    try:
        customer = db.get(CustomerModel, phone.strip())
        if not customer or not customer.otp_hash or not customer.otp_expires_at:
            raise HTTPException(status_code=401, detail="OTP not requested")
        expires = customer.otp_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="OTP expired")
        if not hmac.compare_digest(customer.otp_hash, hashlib.sha256(otp.encode()).hexdigest()):
            raise HTTPException(status_code=401, detail="Invalid OTP")
        if name and name.strip():
            customer.name = name.strip()
        customer.otp_hash = None
        customer.otp_expires_at = None
        db.commit()
        return {"token": create_token(customer.phone, customer.name), "customer": {"phone": customer.phone, "name": customer.name}}
    finally:
        db.close()
