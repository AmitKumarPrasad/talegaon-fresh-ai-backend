import os
from dotenv import load_dotenv

load_dotenv()

REQUIRED_PRODUCTION_VARS = (
    "OPENAI_API_KEY",
    "WHATSAPP_VERIFY_TOKEN",
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_PHONE_NUMBER_ID",
    "SELLER_WHATSAPP_NUMBER",
    "RAZORPAY_KEY_ID",
    "RAZORPAY_KEY_SECRET",
    "RAZORPAY_WEBHOOK_SECRET",
    "ADMIN_API_TOKEN",
    "DATABASE_URL",
)

def validate_production_config() -> None:
    if os.getenv("ENVIRONMENT", "development").lower() != "production":
        return
    missing = [name for name in REQUIRED_PRODUCTION_VARS if not os.getenv(name)]
    if missing:
        raise RuntimeError("Missing required production environment variables: " + ", ".join(missing))
    if os.getenv("DATABASE_URL", "").startswith("sqlite"):
        raise RuntimeError("SQLite is not supported for production. Configure MySQL.")
