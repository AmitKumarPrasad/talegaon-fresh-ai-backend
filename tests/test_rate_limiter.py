import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import Request

from app.rate_limiter import client_ip, enforce_rate_limit, rule_for


def request_for(path: str, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": headers or [],
        "client": ("127.0.0.1", 1234),
        "scheme": "https",
        "server": ("test", 443),
    }
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    return Request(scope, receive)


class RateLimiterTests(unittest.IsolatedAsyncioTestCase):
    def test_rules_cover_sensitive_endpoints(self):
        self.assertEqual(rule_for("/auth/login"), (10, 60))
        self.assertEqual(rule_for("/auth/register"), (5, 600))
        self.assertEqual(rule_for("/auth/google/login"), (10, 60))
        self.assertEqual(rule_for("/auth/google/otp"), (3, 600))
        self.assertEqual(rule_for("/auth/google/register"), (5, 600))
        self.assertEqual(rule_for("/auth/refresh"), (30, 60))
        self.assertEqual(rule_for("/customers/me/ai/chat"), (20, 60))
        self.assertEqual(rule_for("/admin/orders"), (60, 60))
        self.assertIsNone(rule_for("/products"))

    def test_client_ip_prefers_cloudflare_ip(self):
        request = request_for(
            "/auth/login",
            [(b"cf-connecting-ip", b"203.0.113.9"), (b"x-forwarded-for", b"198.51.100.4")],
        )
        self.assertEqual(client_ip(request), "203.0.113.9")

    async def test_blocked_request_returns_429(self):
        fake_redis = type("FakeRedis", (), {})()
        fake_redis.eval = AsyncMock(return_value=[0, 0, 42])
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "REDIS_URL": "redis://test"}):
            with patch("app.rate_limiter._client", return_value=fake_redis):
                response = await enforce_rate_limit(request_for("/auth/login"))
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "42")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    async def test_allowed_request_returns_none(self):
        fake_redis = type("FakeRedis", (), {})()
        fake_redis.eval = AsyncMock(return_value=[1, 9, 55])
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "REDIS_URL": "redis://test"}):
            with patch("app.rate_limiter._client", return_value=fake_redis):
                response = await enforce_rate_limit(request_for("/auth/login"))
        self.assertIsNone(response)
        fake_redis.eval.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()

