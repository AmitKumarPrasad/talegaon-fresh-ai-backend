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
