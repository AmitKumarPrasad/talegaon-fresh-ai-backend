"""SMS delivery via the open-source android-sms-gateway project.

Project: https://github.com/capcom6/android-sms-gateway
Your own Android phone (with a SIM card) runs the gateway app and relays
messages sent through the public cloud relay, so no paid SMS provider is
required. Configure SMS_GATEWAY_USERNAME / SMS_GATEWAY_PASSWORD with the
credentials shown in the app's "Cloud Server" settings.
"""
import os
import requests

SMS_GATEWAY_URL = os.getenv("SMS_GATEWAY_URL", "https://api.sms-gate.app/3rdparty/v1/message")


def send_sms(phone: str, message: str) -> dict:
    username = os.getenv("SMS_GATEWAY_USERNAME")
    password = os.getenv("SMS_GATEWAY_PASSWORD")
    if not username or not password:
        return {"status": "skipped", "reason": "SMS gateway credentials are not configured"}

    response = requests.post(
        SMS_GATEWAY_URL,
        auth=(username, password),
        json={"message": message, "phoneNumbers": [phone]},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()
