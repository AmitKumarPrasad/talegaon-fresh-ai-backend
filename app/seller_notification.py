"""Email notifications for new orders; credentials are supplied by the environment."""
import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def notify_seller(order_id: int, customer_id: str, total: float, address: str, payment_method: str) -> dict:
    host = os.getenv("ORDER_EMAIL_SMTP_HOST", "").strip()
    sender = os.getenv("ORDER_EMAIL_FROM", "").strip()
    recipient = os.getenv("ORDER_EMAIL_TO", "").strip()
    username = os.getenv("ORDER_EMAIL_USERNAME", "").strip()
    password = os.getenv("ORDER_EMAIL_PASSWORD", "")
    if not all((host, sender, recipient, username, password)):
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
    try:
        port = int(os.getenv("ORDER_EMAIL_SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(username, password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException, ValueError):
        # Avoid logging credentials or message content.
        logger.error("Order email failed order_id=%s", order_id)
        return {"status": "failed"}
    return {"status": "sent"}
