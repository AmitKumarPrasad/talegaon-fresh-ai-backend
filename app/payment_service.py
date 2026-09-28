import hashlib
import hmac
import os
from typing import Any

import requests

RAZORPAY_API_BASE = "https://api.razorpay.com/v1"


class PaymentError(RuntimeError):
    pass


def _credentials() -> tuple[str, str]:
    key_id = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise PaymentError("Razorpay credentials are not configured")
    return key_id, key_secret


def create_payment_link(order_id: int, amount: float, customer_id: str) -> dict[str, Any]:
    key_id, key_secret = _credentials()
    payload = {
        "amount": int(round(amount * 100)),
        "currency": "INR",
        "accept_partial": False,
        "reference_id": f"TF-{order_id}",
        "description": f"Talegaon Fresh Order #{order_id}",
        "customer": {"contact": customer_id},
        "notify": {"sms": False, "email": False},
        "reminder_enable": True,
        "notes": {"talegaon_fresh_order_id": str(order_id)},
    }
    response = requests.post(
        f"{RAZORPAY_API_BASE}/payment_links",
        auth=(key_id, key_secret),
        json=payload,
        timeout=15,
    )
    if not response.ok:
        raise PaymentError(f"Razorpay payment link creation failed: HTTP {response.status_code}")
    data = response.json()
    if not data.get("id") or not data.get("short_url"):
        raise PaymentError("Razorpay returned an incomplete payment link response")
    return data


def verify_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET")
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def extract_paid_event(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("event") not in {"payment_link.paid", "payment_link.partially_paid"}:
        return None
    entity = payload.get("payload", {}).get("payment_link", {}).get("entity", {})
    payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
    if not entity or not payment:
        return None
    reference_id = entity.get("reference_id")
    payment_id = payment.get("id")
    link_id = entity.get("id")
    amount = payment.get("amount")
    if not reference_id or not payment_id or not link_id or amount is None:
        return None
    return {
        "event": payload.get("event"),
        "event_id": payload.get("id") or f"{payload.get('event')}:{payment_id}",
        "reference_id": reference_id,
        "payment_link_id": link_id,
        "payment_id": payment_id,
        "amount": int(amount),
        "status": payment.get("status"),
    }
