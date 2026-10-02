import os
from unittest.mock import Mock, patch

from app.msg91_service import send_otp, verify_otp


def test_send_otp_uses_msg91_template_and_e164_phone():
    response = Mock(status_code=200)
    response.json.return_value = {"type": "success", "message": "OTP sent successfully"}

    with patch.dict(
        os.environ,
        {"MSG91_AUTHKEY": "secret", "MSG91_TEMPLATE_ID": "template-123"},
        clear=False,
    ), patch("app.msg91_service.requests.post", return_value=response) as post:
        result = send_otp("9876543210")

    assert result["type"] == "success"
    post.assert_called_once_with(
        "https://control.msg91.com/api/v5/otp",
        params={"template_id": "template-123", "mobile": "+919876543210"},
        headers={"authkey": "secret", "content-type": "application/json"},
        timeout=10,
    )


def test_verify_otp_uses_msg91_provider():
    response = Mock(status_code=200)
    response.json.return_value = {"type": "success", "message": "OTP verified successfully"}

    with patch.dict(os.environ, {"MSG91_AUTHKEY": "secret", "MSG91_TEMPLATE_ID": "template-123"}, clear=False), patch("app.msg91_service.requests.get", return_value=response) as get:
        assert verify_otp("9876543210", "123456") is True

    get.assert_called_once_with(
        "https://control.msg91.com/api/v5/otp/verify",
        params={"otp": "123456", "mobile": "+919876543210"},
        headers={"authkey": "secret"},
        timeout=10,
    )


def test_msg91_requires_credentials():
    with patch.dict(os.environ, {}, clear=True):
        try:
            send_otp("9876543210")
        except RuntimeError as exc:
            assert "MSG91 OTP is not configured" in str(exc)
        else:
            raise AssertionError("Expected missing MSG91 configuration failure")
