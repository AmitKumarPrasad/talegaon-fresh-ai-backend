import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from app.catalog import product_menu
from app.menu import MENU, menu_response
from app.openai_service import generate_reply
from app.order_flow import process_order_message
from app.state import get_state
from app.whatsapp import send_text_message

load_dotenv()
app = FastAPI(title="Talegaon Fresh AI Agent", version="0.4.0")
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

@app.get("/")
def health() -> dict:
    return {"service": "Talegaon Fresh AI Agent", "status": "running"}

@app.get("/menu")
def get_menu() -> dict:
    return {"menu": MENU}

@app.get("/products")
def get_products() -> dict:
    return {"products": product_menu()}

@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == VERIFY_TOKEN:
        return PlainTextResponse(params.get("hub.challenge") or "")
    return PlainTextResponse("Verification failed", status_code=403)

def extract_message(body: dict) -> tuple[str | None, str | None]:
    try:
        value = body["entry"][0]["changes"][0]["value"]
        message = value["messages"][0]
        return message.get("from"), message.get("text", {}).get("body")
    except (KeyError, IndexError, TypeError):
        return None, None

@app.post("/webhook")
async def receive_webhook(request: Request) -> dict:
    body = await request.json()
    customer_id, message = extract_message(body)
    if not customer_id or not message:
        return {"status": "ignored"}

    state = get_state(customer_id)
    response = menu_response(message)

    if response is None:
        result = process_order_message(customer_id, message)
        response = result["message"]
        if result["status"] == "order_created":
            state.step = "address"
    elif message.strip() == "2":
        response = f"🥦 Today's Products\n\n{product_menu()}\n\nSend product name and quantity to order."
        state.step = "products"

    send_result = send_text_message(customer_id, response)
    return {"status": "processed", "reply": response, "whatsapp": send_result, "conversation_step": state.step}
