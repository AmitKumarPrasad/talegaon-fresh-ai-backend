import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException


ADMIN_SESSION_MINUTES = 60


def _secret() -> str:
    return os.getenv("JWT_SECRET", "development-jwt-secret-change-me")


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _ub64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_admin_session(admin_token: str) -> str:
    configured = os.getenv("ADMIN_API_TOKEN")
    if not configured or not hmac.compare_digest(admin_token, configured):
        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    now = datetime.now(timezone.utc)
    header = _b64(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64(json.dumps({
        "sub": "store-admin",
        "role": "admin",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ADMIN_SESSION_MINUTES)).timestamp()),
    }, separators=(",", ":")).encode())
    signing = f"{header}.{payload}".encode()
    signature = hmac.new(_secret().encode(), signing, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64(signature)}"


def is_admin_session(token: str) -> bool:
    try:
        header, payload, signature = token.split(".")
        expected = hmac.new(
            _secret().encode(), f"{header}.{payload}".encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, _ub64(signature)):
            return False
        data = json.loads(_ub64(payload))
        return (
            data.get("sub") == "store-admin"
            and data.get("role") == "admin"
            and int(data.get("exp", 0)) >= int(datetime.now(timezone.utc).timestamp())
        )
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False
