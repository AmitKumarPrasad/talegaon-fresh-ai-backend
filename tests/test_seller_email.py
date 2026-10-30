import base64
import json
from unittest.mock import patch
from urllib.error import URLError

from app.seller_notification import notify_seller


def configure(monkeypatch):
    for key, value in {
        "ORDER_EMAIL_FROM": "sender@example.com",
        "ORDER_EMAIL_TO": "admin@example.com",
        "GMAIL_CLIENT_ID": "client",
        "GMAIL_CLIENT_SECRET": "secret",
        "GMAIL_REFRESH_TOKEN": "refresh",
    }.items():
        monkeypatch.setenv(key, value)


def test_new_order_email_uses_gmail_api(monkeypatch):
    configure(monkeypatch)
    with patch("app.seller_notification._post_json", side_effect=[{"access_token": "access"}, {"id": "sent"}]) as post:
        assert notify_seller(12, "customer", 499, "address", "COD")["status"] == "sent"
    assert post.call_count == 2
    url, body, headers = post.call_args.args
    assert url == "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    assert headers["Authorization"] == "Bearer access"
    msg = base64.urlsafe_b64decode(json.loads(body)["raw"]).decode()
    assert "admin@example.com" in msg
    assert "#12" in msg
    assert "499.00" in msg


def test_unconfigured_email_is_skipped(monkeypatch):
    monkeypatch.delenv("ORDER_EMAIL_TO", raising=False)
    assert notify_seller(1, "customer", 10, "address", "COD")["status"] == "skipped"


def test_api_failure_is_reported_without_raising(monkeypatch):
    configure(monkeypatch)
    with patch("app.seller_notification._post_json", side_effect=URLError("failed")):
        assert notify_seller(1, "customer", 10, "address", "COD")["status"] == "failed"
