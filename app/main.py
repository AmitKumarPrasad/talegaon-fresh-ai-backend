import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from app.menu import MENU, menu_response
from app.openai_service import generate_reply

load_dotenv()

app = FastAPI(title="Talegaon Fresh AI Agent", version="0.2.0")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")


@app.get("/")
def health() -> dict:
    return {"service": "Talegaon Fresh AI Agent", "status": "running"}


@app.get("/menu")
def get_menu() -> dict:
    return {"menu": MENU}


@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge or "")

    return PlainTextResponse("Verification failed", status_code=403)


def extract_message_text(body: dict) -> str | None:
    try:
        value = body["entry"][0]["changes"][0]["value"]
        message = value["messages"][0]
        return message.get("text", {}).get("body")
    except (KeyError, IndexError, TypeError):
        return None


@app.post("/webhook")
async def receive_webhook(request: Request) -> dict:
    body = await request.json()
    message = extract_message_text(body)

    if not message:
        return {"status": "ignored"}

    response = menu_response(message)
    if response is None:
        response = generate_reply(message)

    print("Incoming:", message)
    print("Outgoing:", response)

    # WhatsApp outbound API integration will be added in the next phase.
    return {"status": "processed", "reply": response}
