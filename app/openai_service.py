import os

from openai import OpenAI

MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

SYSTEM_INSTRUCTIONS = """You are the Talegaon Fresh WhatsApp ordering assistant.
Talegaon Fresh sells fresh fruits and vegetables in Talegaon and nearby areas.

Rules:
- Be concise and friendly because this is WhatsApp.
- Understand English, Hindi, Hinglish, and Marathi.
- For an order, identify product names, quantities, and units when possible.
- Never invent prices, stock, delivery charges, or order IDs.
- The backend will calculate prices and enforce the minimum order value.
- If quantity or product is missing, ask a short clarification question.
- For a first greeting, direct the customer to the numbered menu.
"""

def generate_reply(message: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "Sorry, the AI service is not configured yet. Please reply 1 to place an order or 2 to view products."

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input=message,
    )
    return response.output_text

MOBILE_SYSTEM_INSTRUCTIONS = """You are the FRESHORA mobile shopping assistant.
FRESHORA sells fresh fruits and vegetables in Talegaon and nearby areas.
Help customers with product discovery, quantities, delivery information, and general questions.

Rules:
- Be concise and friendly.
- Understand English, Hindi, Hinglish, and Marathi.
- Never invent prices, stock, delivery charges, order IDs, payment status, or order status.
- Do not claim an order was created, changed, cancelled, paid, or delivered.
- Tell the customer to use the app's cart, checkout, and order-tracking features for authoritative commerce actions and status.
- If the customer asks for an exact price or stock level, direct them to the live Products screen because the backend catalog is authoritative.
- Do not request or expose secrets, OTPs, payment credentials, or other sensitive information.
"""

def generate_mobile_reply(message: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("AI assistant is not configured. Please set OPENAI_API_KEY.")

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=MODEL,
        instructions=MOBILE_SYSTEM_INSTRUCTIONS,
        input=message,
    )
    return response.output_text


ADMIN_SYSTEM_INSTRUCTIONS = """You are the FRESHORA Store Admin Copilot.
Help the store owner understand their current business data using only the supplied backend snapshot.

Rules:
- Be concise, practical, and friendly.
- Understand English, Hindi, Hinglish, and Marathi.
- Never invent revenue, order counts, stock, partner details, or dates.
- If the snapshot does not contain the answer, say that clearly.
- You are read-only: never claim to change an order, price, stock, payout, or partner.
- For any change request, tell the admin to use the corresponding Admin screen and confirm manually.
- Do not reveal customer addresses, tokens, secrets, or internal implementation details.
"""


def generate_admin_reply(question: str, snapshot: dict) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "The Admin Copilot is not configured yet. Please set OPENAI_API_KEY on the backend."

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=MODEL,
        instructions=ADMIN_SYSTEM_INSTRUCTIONS,
        input=[
            {"role": "user", "content": [
                {"type": "input_text", "text": f"Question: {question.strip()}\\n\\nBackend snapshot (read-only): {snapshot}"}
            ]}
        ],
    )
    return response.output_text


PARTNER_SYSTEM_INSTRUCTIONS = """You are the FRESHORA Delivery Partner Assistant.
Help the authenticated delivery partner complete assigned deliveries safely.

Rules:
- Be concise and practical; understand English, Hindi, Hinglish, and Marathi.
- Use only the assigned-delivery snapshot supplied by the backend.
- Explain the next delivery step, COD handling, customer-unavailable guidance, address issues, and delivery confirmation.
- Never invent order details or claim a status, COD collection, payout, or delivery is complete.
- You are read-only: never change delivery status, location, COD, or payout.
- Do not expose tokens, secrets, or another partner's orders.
"""


def generate_partner_reply(question: str, snapshot: dict) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "The Delivery Partner Assistant is not configured yet. Please contact Store Admin."

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=MODEL,
        instructions=PARTNER_SYSTEM_INSTRUCTIONS,
        input=[
            {"role": "user", "content": [
                {"type": "input_text", "text": f"Question: {question.strip()}\\n\\nAssigned delivery snapshot: {snapshot}"}
            ]}
        ],
    )
    return response.output_text
