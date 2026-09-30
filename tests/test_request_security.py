import unittest
from starlette.requests import Request
from starlette.responses import Response

from app.main import _apply_security_headers, _request_id


def _request(headers=None):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/health",
        "headers": [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()],
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
    }
    return Request(scope)


class RequestSecurityTests(unittest.TestCase):
    def test_request_id_is_generated_when_missing(self):
        request = _request()
        request_id = _request_id(request)
        self.assertEqual(request_id, request.state.request_id)
        self.assertEqual(len(request_id), 32)

    def test_valid_client_request_id_is_reused(self):
        request = _request({"X-Request-ID": "mobile-login-123"})
        self.assertEqual(_request_id(request), "mobile-login-123")

    def test_invalid_client_request_id_is_replaced(self):
        request = _request({"X-Request-ID": "bad request/id"})
        request_id = _request_id(request)
        self.assertNotEqual(request_id, "bad request/id")
        self.assertEqual(len(request_id), 32)

    def test_security_headers_apply_to_all_responses(self):
        request = _request()
        _request_id(request)
        response = _apply_security_headers(request, Response(status_code=429))
        self.assertEqual(response.headers["X-Request-ID"], request.state.request_id)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(
            response.headers["Permissions-Policy"],
            "camera=(), microphone=(), geolocation=(self)",
        )


if __name__ == "__main__":
    unittest.main()
