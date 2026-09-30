import pytest
from starlette.requests import Request

from app import rate_limiter


class _Connection:
    def execute(self, statement):
        return None


class _Engine:
    def connect(self):
        return self

    def __enter__(self):
        return _Connection()

    def __exit__(self, exc_type, exc, tb):
        return False


def _request(path: str) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_readiness_returns_ready_when_database_and_redis_are_available(monkeypatch):
    import app.db

    monkeypatch.setattr(app.db, "engine", _Engine())

    async def redis_ok():
        return None

    monkeypatch.setattr(rate_limiter, "check_redis", redis_ok)

    response = await rate_limiter.readiness_response(_request("/ready"))

    assert response is not None
    assert response.status_code == 200
    assert response.body == (
        b'{"service":"Talegaon Fresh AI Agent","status":"ready",'
        b'"dependencies":{"database":"ok","redis":"ok"}}'
    )


@pytest.mark.asyncio
async def test_readiness_returns_503_when_a_dependency_is_unavailable(monkeypatch):
    import app.db

    class _BrokenEngine:
        def connect(self):
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(app.db, "engine", _BrokenEngine())

    async def redis_down():
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(rate_limiter, "check_redis", redis_down)

    response = await rate_limiter.readiness_response(_request("/ready"))

    assert response is not None
    assert response.status_code == 503
    assert response.body == (
        b'{"service":"Talegaon Fresh AI Agent","status":"not_ready",'
        b'"dependencies":{"database":"unavailable","redis":"unavailable"}}'
    )


@pytest.mark.asyncio
async def test_non_readiness_path_is_ignored():
    response = await rate_limiter.readiness_response(_request("/health"))

    assert response is None
