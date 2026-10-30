from unittest.mock import MagicMock, patch
import smtplib

from app.seller_notification import notify_seller


def test_new_order_email_uses_tls_and_sends_to_admin(monkeypatch):
    for key, value in {
        "ORDER_EMAIL_SMTP_HOST": "smtp.example.com",
        "ORDER_EMAIL_SMTP_PORT": "587",
        "ORDER_EMAIL_FROM": "sender@example.com",
        "ORDER_EMAIL_TO": "admin@example.com",
        "ORDER_EMAIL_USERNAME": "sender@example.com",
        "ORDER_EMAIL_PASSWORD": "test-secret",
    }.items():
        monkeypatch.setenv(key, value)
    server = MagicMock()
    with patch("app.seller_notification.smtplib.SMTP") as smtp:
        smtp.return_value.__enter__.return_value = server
        result = notify_seller(12, "customer", 499, "address", "COD")
    assert result["status"] == "sent"
    smtp.assert_called_once_with("smtp.example.com", 587, timeout=10)
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("sender@example.com", "test-secret")
    msg = server.send_message.call_args.args[0]
    assert msg["To"] == "admin@example.com"
    assert "#12" in msg["Subject"]
    assert "499.00" in msg.get_content()


def test_unconfigured_email_is_skipped(monkeypatch):
    monkeypatch.delenv("ORDER_EMAIL_TO", raising=False)
    assert notify_seller(1, "customer", 10, "address", "COD")["status"] == "skipped"


def test_smtp_failure_is_reported_without_raising(monkeypatch):
    for key in ("ORDER_EMAIL_SMTP_HOST", "ORDER_EMAIL_FROM", "ORDER_EMAIL_TO",
                "ORDER_EMAIL_USERNAME", "ORDER_EMAIL_PASSWORD"):
        monkeypatch.setenv(key, "configured")
    with patch("app.seller_notification.smtplib.SMTP", side_effect=smtplib.SMTPException("failed")):
        assert notify_seller(1, "customer", 10, "address", "COD")["status"] == "failed"
