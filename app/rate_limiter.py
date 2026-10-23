import os
import hashlib

from app.config import is_production_environment

from fastapi import Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

_WINDOW_RULES = {
    "/auth/login": (10, 60),
    "/partner/auth/login": (10, 60),
    "/partner/auth/refresh": (30, 60),
    "/partner/ai/assistant": (20, 60),
    "/auth/register": (5, 600),
    "/auth/google/login": (10, 60),
    "/auth/google/otp": (3, 600),
    "/auth/google/register": (5, 600),
    "/auth/refresh": (30, 60),
    "/auth/request-otp": (5, 600),
    "/auth/verify-otp": (10, 600),
    "/customers/me/ai/chat": (20, 60),
}
_ADMIN_RULE = (60, 60)

_RATE_SCRIPT = """
local current = redis.call('GET', KEYS[1])
if not current then
  redis.call('SET', KEYS[1], 1, 'EX', ARGV[2])
  return {1, ARGV[1] - 1, ARGV[2]}
end
current = redis.call('INCR', KEYS[1])
local ttl = redis.call('TTL', KEYS[1])
if current <= tonumber(ARGV[1]) then
  return {1, tonumber(ARGV[1]) - current, ttl}
end
return {0, 0, ttl}
"""

_redis: Redis | None = None


def _environment() -> str:
    return "production" if is_production_environment() else os.getenv("ENVIRONMENT", "development").lower()


def _client() -> Redis:
    global _redis
    if _redis is None:
        url = os.getenv("REDIS_URL")
        if not url:
            raise RuntimeError("REDIS_URL is required for production rate limiting.")
        _redis = Redis.from_url(url, decode_responses=False)
    return _redis


async def check_redis() -> None:
    await _client().ping()


async def readiness_response(request: Request) -> JSONResponse | None:
    if request.url.path != "/ready":
        return None

    database_ok = False
    redis_ok = False
    try:
        from sqlalchemy import text
        from app.db import engine

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database_ok = True
    except Exception:
        database_ok = False

    try:
        await check_redis()
        redis_ok = True
    except Exception:
        redis_ok = False

    if database_ok and redis_ok:
        return JSONResponse(
            {
                "service": "Talegaon Fresh AI Agent",
                "status": "ready",
                "dependencies": {"database": "ok", "redis": "ok"},
            }
        )

    return JSONResponse(
        {
            "service": "Talegaon Fresh AI Agent",
            "status": "not_ready",
            "dependencies": {
                "database": "ok" if database_ok else "unavailable",
                "redis": "ok" if redis_ok else "unavailable",
            },
        },
        status_code=503,
        headers={"Cache-Control": "no-store"},
    )


def client_ip(request: Request) -> str:
    # Render's public edge provides CF-Connecting-IP. Fall back to the
    # first X-Forwarded-For value when Cloudflare's header is unavailable.
    cloudflare_ip = request.headers.get("CF-Connecting-IP", "").strip()
    if cloudflare_ip:
        return cloudflare_ip
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def rule_for(path: str) -> tuple[int, int] | None:
    if path == "/mcp" or path.startswith("/mcp/"):
        return (30, 60)
    if path.startswith(("/admin/", "/partner/admin/")):
        return _ADMIN_RULE
    return _WINDOW_RULES.get(path)


async def enforce_rate_limit(request: Request) -> JSONResponse | None:
    readiness = await readiness_response(request)
    if readiness is not None:
        return readiness

    rule = rule_for(request.url.path)
    if not rule:
        return None

    limit, window = rule
    key = f"tf:rl:v1:{request.url.path}:{client_ip(request)}"
    try:
        result = await _client().eval(_RATE_SCRIPT, 1, key, limit, window)
        # Account-level ceiling also protects PIN login across different IPs.
        if int(result[0]) and request.url.path in {"/auth/login", "/partner/auth/login", "/auth/google/otp", "/auth/google/register"}:
            try:
                payload = await request.json()
                phone = str(payload.get("phone", "")).strip()
            except (ValueError, TypeError, AttributeError):
                phone = ""
            if phone:
                account = hashlib.sha256(phone.encode()).hexdigest()
                account_key = f"tf:rl:account:{request.url.path}:{account}"
                account_limit, account_window = {
                    "/auth/google/otp": (3, 600),
                    "/auth/google/register": (5, 600),
                }.get(request.url.path, (5, 900))
                result = await _client().eval(_RATE_SCRIPT, 1, account_key, account_limit, account_window)
    except Exception:
        if _environment() == "production":
            return JSONResponse(
                {"detail": "Rate limiting service is temporarily unavailable."},
                status_code=503,
                headers={"Cache-Control": "no-store"},
            )
        return None

    allowed = int(result[0])
    remaining = max(0, int(result[1]))
    retry_after = max(1, int(result[2]))
    if allowed:
        return None

    return JSONResponse(
        {"detail": "Too many requests. Please try again later."},
        status_code=429,
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "Cache-Control": "no-store",
        },
    )

