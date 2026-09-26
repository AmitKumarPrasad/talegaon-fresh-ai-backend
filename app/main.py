import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

load_dotenv()

app = FastAPI(title="Talegaon Fresh AI Agent", version="0.1.0")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

@app.get("/")
def health() -> dict:
    return {"service": "Talegaon Fresh AI Agent", "status": "running"}

@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    if mode == "subscribe" and token and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge or "")
    return PlainTextResponse("Verification failed", status_code=403)

@app.post("/webhook")
async def receive_webhook(request: Request) -> dict:
    body = await request.json()
    print("WhatsApp webhook received:", body)
    return {"status": "received"}
