import json
import os
from openai import OpenAI

SYSTEM = """Extract a Talegaon Fresh vegetable/fruit order from the customer message.
Return JSON only with this shape:
{"items":[{"product":"Tomato","quantity":2,"unit":"kg"}]}
Do not invent products. Normalize common Hindi, Hinglish and Marathi names to the English catalog names when clear.
If quantity or product is unclear, omit that item.
"""

def extract_order(message: str) -> dict:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return {"items": []}
    client = OpenAI(api_key=key)
    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
        instructions=SYSTEM,
        input=message,
    )
    try:
        return json.loads(response.output_text)
    except json.JSONDecodeError:
        return {"items": []}
