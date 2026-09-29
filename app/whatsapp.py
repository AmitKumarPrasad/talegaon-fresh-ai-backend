import os
import requests

from app.phone_utils import to_e164_digits

GRAPH_API_VERSION = os.getenv("WHATSAPP_GRAPH_API_VERSION", "v23.0")


def send_text_message(to: str, text: str) -> dict:
    token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
    if not token or not phone_number_id:
        return {"status": "skipped", "reason": "WhatsApp credentials are not configured"}

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_e164_digits(to),
        "type": "text",
        "text": {"body": text},
    }
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )
    if not response.ok:
        raise requests.exceptions.HTTPError(
            f"{response.status_code} error sending WhatsApp message: {response.text}", response=response
        )
    return response.json()
