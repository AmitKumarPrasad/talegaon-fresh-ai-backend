import os
from types import SimpleNamespace
from unittest.mock import patch

from app.twilio_service import send_otp_sms


def test_send_otp_sms_uses_twilio_and_e164_phone():
    with patch.dict(
        os.environ,
        {
            "ENVIRONMENT": "production",
            "TWILIO_ACCOUNT_SID": "AC123",
            "TWILIO_AUTH_TOKEN": "secret",
            "TWILIO_FROM_NUMBER": "+15551234567",
        },
        clear=False,
    ), patch("twilio.rest.Client") as client_class:
        client_class.return_value.messages.create.return_value = SimpleNamespace(sid="SM123")

        result = send_otp_sms("9876543210", "123456")

        assert result == {"status": "sent", "message_sid": "SM123"}
        client_class.assert_called_once_with("AC123", "secret")
        client_class.return_value.messages.create.assert_called_once_with(
            body="Your Talegaon Fresh OTP is 123456. It expires in 5 minutes.",
            from_="+15551234567",
            to="+919876543210",
        )


def test_send_otp_sms_requires_twilio_in_production():
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=False):
        for key in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER"):
            os.environ.pop(key, None)
        try:
            send_otp_sms("9876543210", "123456")
        except RuntimeError as exc:
            assert "Twilio SMS is not configured" in str(exc)
        else:
            raise AssertionError("Expected production Twilio configuration failure")
