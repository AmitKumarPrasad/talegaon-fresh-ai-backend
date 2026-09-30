"""Production configuration validation.

Core mobile commerce remains available without external-provider credentials.
Optional AI functionality uses OPENAI_API_KEY when configured.
WhatsApp and Razorpay integrations remain in the codebase for later use but
are not required to start the mobile-focused production service.
"""
import os
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

REQUIRED_PRODUCTION_VARS = (
    "ADMIN_API_TOKEN",
    "DATABASE_URL",
    "JWT_SECRET",
    "REDIS_URL",
)

OPTIONAL_PRODUCTION_VARS = (
    "OPENAI_API_KEY",
    "WHATSAPP_VERIFY_TOKEN",
    "WHATSAPP_APP_SECRET",
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_PHONE_NUMBER_ID",
    "SELLER_WHATSAPP_NUMBER",
    "RAZORPAY_KEY_ID",
    "RAZORPAY_KEY_SECRET",
    "RAZORPAY_WEBHOOK_SECRET",
    "MSG91_AUTHKEY",
    "MSG91_TEMPLATE_ID",
)


def get_cors_allowed_origins() -> list[str]:
    """Return validated CORS origins from CORS_ALLOWED_ORIGINS."""
    environment = os.getenv("ENVIRONMENT", "development").lower()
    default = "" if environment == "production" else "*"
    raw = os.getenv("CORS_ALLOWED_ORIGINS", default)
    origins = [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]

    if environment == "production":
        if "*" in origins:
            raise RuntimeError("CORS_ALLOWED_ORIGINS must not contain '*' in production.")
        for origin in origins:
            parsed = urlparse(origin)
            if parsed.scheme != "https" or not parsed.netloc:
                raise RuntimeError(
                    "Production CORS_ALLOWED_ORIGINS must contain only explicit HTTPS origins."
                )
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise RuntimeError(
                    "Production CORS origins must not contain credentials, query parameters, or fragments."
                )
            if parsed.path not in ("", "/"):
                raise RuntimeError(
                    "Production CORS origins must not contain URL paths."
                )

    return origins


def validate_production_config() -> None:
    if os.getenv("ENVIRONMENT", "development").lower() != "production":
        return

    missing = [name for name in REQUIRED_PRODUCTION_VARS if not os.getenv(name)]
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

    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url.startswith(("redis://", "rediss://")):
        raise RuntimeError(
            "Production REDIS_URL must use Redis (redis:// or rediss://)."
        )

    jwt_secret = os.getenv("JWT_SECRET", "")
    if len(jwt_secret) < 32 or jwt_secret == "development-jwt-secret-change-me":
        raise RuntimeError(
            "Production JWT_SECRET must be a unique secret of at least 32 characters."
        )
