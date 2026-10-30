from unittest.mock import patch
from urllib.error import HTTPError

from app.seller_notification import notify_seller


def test_logs_stage_and_status_without_secrets(monkeypatch, caplog):
    for key in ("ORDER_EMAIL_FROM", "ORDER_EMAIL_TO", "GMAIL_CLIENT_ID",
                "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"):
        monkeypatch.setenv(key, "configured")
    error = HTTPError("https://example.invalid", 401, "sensitive response", {}, None)
    with patch("app.seller_notification._post_json", side_effect=[{"access_token": "private-token"}, error]):
        assert notify_seller(12, "customer", 499, "address", "COD")["status"] == "failed"
    assert "stage=gmail_send" in caplog.text
    assert "http_status=401" in caplog.text
    assert "private-token" not in caplog.text
    assert "sensitive response" not in caplog.text
