"""Twilio SMS delivery for customer OTPs."""
import os

from app.phone_utils import to_e164


def send_otp_sms(phone: str, otp: str) -> dict:
    """Send an OTP using Twilio Programmable Messaging.

    Development keeps the existing demo OTP flow when Twilio credentials are
    absent. Production configuration validation requires the Twilio settings.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")

    if not account_sid or not auth_token or not from_number:
        if os.getenv("ENVIRONMENT", "development").lower() == "production":
            raise RuntimeError("Twilio SMS is not configured. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER.")
        return {"status": "skipped", "reason": "Twilio credentials are not configured"}

    from twilio.rest import Client

    client = Client(account_sid, auth_token)
    message = client.messages.create(
        body=f"Your Talegaon Fresh OTP is {otp}. It expires in 5 minutes.",
        from_=from_number,
        to=to_e164(phone),
    )
    return {"status": "sent", "message_sid": message.sid}
