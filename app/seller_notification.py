"""Send new order alerts using the Gmail API over HTTPS."""
import base64
import json
import logging
import os
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


def _post_json(url, data, headers):
    request = Request(url, data=data, headers=headers, method="POST")
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def notify_seller(order_id: int, customer_id: str, total: float, address: str, payment_method: str) -> dict:
    sender = os.getenv("ORDER_EMAIL_FROM", "").strip()
    recipient = os.getenv("ORDER_EMAIL_TO", "").strip()
    client_id = os.getenv("GMAIL_CLIENT_ID", "").strip()
    client_secret = os.getenv("GMAIL_CLIENT_SECRET", "")
    refresh_token = os.getenv("GMAIL_REFRESH_TOKEN", "")
    if not all((sender, recipient, client_id, client_secret, refresh_token)):
        logger.warning("Order email not configured; notification skipped order_id=%s", order_id)
        return {"status": "skipped", "reason": "Order email not configured"}

    message = EmailMessage()
    message["Subject"] = f"Freshora: New order #{order_id}"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        f"A new Freshora order has been placed.\n\n"
        f"Order number: #{order_id}\n"
        f"Total: ₹{total:.2f}\n"
        f"Payment method: {payment_method}\n\n"
        "Open the Freshora admin panel to review the order and assign a partner.\n"
    )
    stage = "oauth_refresh"
    try:
        token = _post_json(
            "https://oauth2.googleapis.com/token",
            urlencode({"client_id": client_id, "client_secret": client_secret,
                       "refresh_token": refresh_token, "grant_type": "refresh_token"}).encode(),
            {"Content-Type": "application/x-www-form-urlencoded"},
        )["access_token"]
        stage = "gmail_send"
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        _post_json(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
            json.dumps({"raw": raw}).encode(),
            {"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        )
    except HTTPError as exc:
        logger.error("Order email failed order_id=%s stage=%s http_status=%s", order_id, stage, exc.code)
        return {"status": "failed"}
    except (OSError, URLError, ValueError, KeyError) as exc:
        logger.error("Order email failed order_id=%s stage=%s error_type=%s", order_id, stage, type(exc).__name__)
        return {"status": "failed"}
    return {"status": "sent"}
