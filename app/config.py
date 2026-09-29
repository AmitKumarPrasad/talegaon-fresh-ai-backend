"""Production configuration validation.

Core mobile commerce remains available without external-provider credentials.
Optional AI functionality uses OPENAI_API_KEY when configured.
WhatsApp and Razorpay integrations remain in the codebase for later use but
are not required to start the mobile-focused production service.
"""
import os
from dotenv import load_dotenv

load_dotenv()

REQUIRED_PRODUCTION_VARS = (
    "ADMIN_API_TOKEN",
    "DATABASE_URL",
    "JWT_SECRET",
)

OPTIONAL_PRODUCTION_VARS = (
    "OPENAI_API_KEY",
    "WHATSAPP_VERIFY_TOKEN",
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_PHONE_NUMBER_ID",
    "SELLER_WHATSAPP_NUMBER",
    "RAZORPAY_KEY_ID",
    "RAZORPAY_KEY_SECRET",
    "RAZORPAY_WEBHOOK_SECRET",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_FROM_NUMBER",
)


def get_cors_allowed_origins() -> list[str]:
    """Return allowed CORS origins from CORS_ALLOWED_ORIGINS (comma-separated), default '*'."""
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "*")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or ["*"]


def validate_production_config() -> None:
    if os.getenv("ENVIRONMENT", "development").lower() != "production":
        return

    required = REQUIRED_PRODUCTION_VARS + ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER")\n    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Missing required production environment variables: " + ", ".join(missing)
        )

    database_url = os.getenv("DATABASE_URL", "")
    if database_url.startswith("sqlite"):
        raise RuntimeError("SQLite is not supported for production. Configure PostgreSQL.")
    if not database_url.startswith(
        ("postgresql://", "postgres://", "postgresql+psycopg2://")
    ):
        raise RuntimeError("Production DATABASE_URL must use PostgreSQL.")

    jwt_secret = os.getenv("JWT_SECRET", "")
    if len(jwt_secret) < 32 or jwt_secret == "development-jwt-secret-change-me":
        raise RuntimeError(
            "Production JWT_SECRET must be a unique secret of at least 32 characters."
        )
