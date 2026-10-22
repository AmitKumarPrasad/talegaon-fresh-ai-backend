import base64, hashlib, hmac, json, os, secrets
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from app.db import Base, SessionLocal
from app.models import CustomerModel
from app.phone_utils import is_valid_indian_mobile
from app.reviewer import is_reviewer
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

ACCESS_TOKEN_MINUTES = 30
REFRESH_TOKEN_DAYS = 90
MAX_FAILED = 5
LOCK_MINUTES = 15

class PinCredentialModel(Base):
    __tablename__ = "customer_pin_credentials"
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.phone"), primary_key=True)
    pin_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class CustomerSessionModel(Base):
    __tablename__ = "customer_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.phone"), index=True)
    device_id: Mapped[str] = mapped_column(String(200), nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

def _secret() -> str:
    return os.getenv("JWT_SECRET", "development-jwt-secret-change-me")

def _b64(v: bytes) -> str:
    return base64.urlsafe_b64encode(v).rstrip(b"=").decode()

def _ub64(v: str) -> bytes:
    return base64.urlsafe_b64decode(v + "=" * (-len(v) % 4))

def _pin_hash(pin: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(pin.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + _b64(salt) + "$" + _b64(digest)

def _pin_matches(pin: str, encoded: str) -> bool:
    try:
        algorithm, salt, expected = encoded.split("$")
        if algorithm != "scrypt": return False
        actual = hashlib.scrypt(pin.encode(), salt=_ub64(salt), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(actual, _ub64(expected))
    except (ValueError, TypeError):
        return False

def _token(phone: str, name: str, version: int, session_hash: str) -> str:
    now = datetime.now(timezone.utc)
    header = _b64(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64(json.dumps({"sub": phone, "name": name, "ver": version, "sid": session_hash, "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=ACCESS_TOKEN_MINUTES)).timestamp())}, separators=(",", ":")).encode())
    signing = (header + "." + payload).encode()
    signature = hmac.new(_secret().encode(), signing, hashlib.sha256).digest()
    return header + "." + payload + "." + _b64(signature)

def _refresh_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def _issue(db, customer: CustomerModel, device_id: str) -> dict:
    refresh = secrets.token_urlsafe(48)
    session_hash = _refresh_hash(refresh)
    db.add(CustomerSessionModel(customer_id=customer.phone, device_id=device_id, refresh_token_hash=session_hash, expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS)))
    return {"access_token": _token(customer.phone, customer.name, customer.auth_version, session_hash), "refresh_token": refresh, "token_type": "bearer", "expires_in": ACCESS_TOKEN_MINUTES * 60, "customer": {"phone": customer.phone, "name": customer.name, "is_reviewer": is_reviewer(customer.phone)}}

def register(phone: str, name: str, pin: str, device_id: str) -> dict:
    phone = phone.strip()
    if not is_valid_indian_mobile(phone): raise HTTPException(400, "Enter a valid 10-digit Indian mobile number")
    if not device_id or len(device_id) < 16 or len(device_id) > 200: raise HTTPException(400, "Invalid registration data")
    if not pin.isdigit() or len(pin) != 6: raise HTTPException(400, "PIN must be exactly 6 digits")
    db=SessionLocal()
    try:
        customer=db.get(CustomerModel, phone.strip())
        if customer: raise HTTPException(409, "Account already exists. Contact support to securely set up or recover your PIN.")
        if not customer:
            customer=CustomerModel(phone=phone.strip(), name=name.strip() or "Customer"); db.add(customer); db.flush()
        cred=PinCredentialModel(customer_id=customer.phone, pin_hash=_pin_hash(pin))
        db.add(cred)
        result=_issue(db, customer, device_id); db.commit(); return result
    finally: db.close()

def login(phone: str, pin: str, device_id: str) -> dict:
    phone = phone.strip()
    if not is_valid_indian_mobile(phone): raise HTTPException(400, "Enter a valid 10-digit Indian mobile number")
    db=SessionLocal()
    try:
        customer=db.get(CustomerModel, phone.strip())
        cred=db.get(PinCredentialModel, phone.strip())
        if not customer or not cred: raise HTTPException(401, "Invalid mobile number or PIN")
        now=datetime.now(timezone.utc)
        locked=cred.locked_until
        if locked and locked.tzinfo is None: locked=locked.replace(tzinfo=timezone.utc)
        if locked and locked > now: raise HTTPException(429, "Too many failed attempts. Try again later.")
        if not _pin_matches(pin, cred.pin_hash):
            cred.failed_attempts += 1
            if cred.failed_attempts >= MAX_FAILED:
                cred.locked_until=now+timedelta(minutes=LOCK_MINUTES); db.commit()
                raise HTTPException(429, "Too many failed attempts. Try again later.")
            db.commit(); raise HTTPException(401, "Invalid mobile number or PIN")
        cred.failed_attempts=0; cred.locked_until=None
        result=_issue(db, customer, device_id); db.commit(); return result
    finally: db.close()

def refresh(refresh_token: str, device_id: str) -> dict:
    db=SessionLocal()
    try:
        row=db.query(CustomerSessionModel).filter(CustomerSessionModel.refresh_token_hash==_refresh_hash(refresh_token), CustomerSessionModel.revoked_at.is_(None)).first()
        if not row: raise HTTPException(401, "Invalid refresh session")
        expires=row.expires_at
        if expires.tzinfo is None: expires=expires.replace(tzinfo=timezone.utc)
        if expires <= datetime.now(timezone.utc): raise HTTPException(401, "Refresh session expired")
        if not hmac.compare_digest(row.device_id, device_id): row.revoked_at=datetime.now(timezone.utc); db.commit(); raise HTTPException(401, "Session device mismatch")
        customer=db.get(CustomerModel,row.customer_id)
        if not customer: raise HTTPException(401, "Customer not found")
        row.revoked_at=datetime.now(timezone.utc)
        result=_issue(db,customer,device_id); db.commit(); return result
    finally: db.close()

def revoke(refresh_token: str) -> None:
    db=SessionLocal()
    try:
        row=db.query(CustomerSessionModel).filter(CustomerSessionModel.refresh_token_hash==_refresh_hash(refresh_token), CustomerSessionModel.revoked_at.is_(None)).first()
        if row:
            row.revoked_at = datetime.now(timezone.utc)
            customer = db.get(CustomerModel, row.customer_id)
            if customer:
                # The account has one stored push token, which must not remain
                # attached after a device session is explicitly signed out.
                customer.fcm_token = None
            db.commit()
    finally: db.close()


