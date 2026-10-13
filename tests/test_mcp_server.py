import json
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_token
from app.db import Base
from app.models import CustomerModel, OrderModel, ProductModel
from app.mcp_server import build_mcp
from app.rate_limiter import rule_for


@pytest.fixture
def mcp_client(monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "testserver")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://trusted.example")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        db.add_all([
            CustomerModel(phone="919999999991", name="Owner", auth_version=1),
            CustomerModel(phone="919999999992", name="Other", auth_version=1),
            ProductModel(id=1, name="Tomato", unit="kg", category="Vegetables", price=55, in_stock=True, stock_quantity=10),
            OrderModel(id=101, customer_id="919999999991", status="CONFIRMED", total=55, payment_method="COD", address="PRIVATE ADDRESS"),
        ])
        db.commit()
    server, transport = build_mcp()

    @asynccontextmanager
    async def lifespan(app):
        async with server.session_manager.run():
            yield

    app = FastAPI(lifespan=lifespan)
    app.mount("/mcp", transport)
    with patch("app.auth.SessionLocal", sessions), patch("app.mcp_server.SessionLocal", sessions), patch("app.order_details.SessionLocal", sessions):
        with TestClient(app) as client:
            client.headers.update({"Accept": "application/json, text/event-stream", "Authorization": "Bearer " + create_token("919999999991", "Owner")})
            yield client, sessions
    engine.dispose()


def rpc(client, method, params=None):
    return client.post("/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})


def call(client, name, arguments=None):
    response = rpc(client, "tools/call", {"name": name, "arguments": arguments or {}})
    assert response.status_code == 200, response.text
    return response.json()["result"]


def payload(result):
    return json.loads(result["content"][0]["text"])


def test_initialize_and_discover_only_readonly_tools(mcp_client):
    client, _ = mcp_client
    response = rpc(client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})
    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "FRESHORA Customer Tools"
    tools = rpc(client, "tools/list").json()["result"]["tools"]
    assert {tool["name"] for tool in tools} == {"search_products", "get_my_order_status"}
    assert all(tool["annotations"]["readOnlyHint"] for tool in tools)
    assert all("ctx" not in tool["inputSchema"]["properties"] for tool in tools)


def test_catalog_reads_actual_price_and_limits(mcp_client):
    client, _ = mcp_client
    result = payload(call(client, "search_products", {"query": "tom", "limit": 1}))
    assert result["products"][0]["price"] == 55
    assert result["currency"] == "INR"
    assert call(client, "search_products", {"limit": 1000})["isError"]
    assert payload(call(client, "search_products", {"query": "%"}))["products"] == []


def test_customer_scope_and_private_field_redaction(mcp_client):
    client, _ = mcp_client
    result = call(client, "get_my_order_status", {"order_id": 101})
    assert payload(result)["status"] == "CONFIRMED"
    assert "PRIVATE ADDRESS" not in json.dumps(result)
    assert "919999999991" not in json.dumps(result)
    client.headers["Authorization"] = "Bearer " + create_token("919999999992", "Other")
    other = call(client, "get_my_order_status", {"order_id": 101})
    missing = call(client, "get_my_order_status", {"order_id": 999})
    assert other["isError"] and missing["isError"]
    assert other["content"] == missing["content"]


def test_missing_forged_and_revoked_sessions_rejected(mcp_client):
    client, sessions = mcp_client
    for authorization in ("", "Bearer forged"):
        client.headers["Authorization"] = authorization
        assert rpc(client, "tools/list").status_code == 401
    client.headers["Authorization"] = "Bearer " + create_token("919999999991", "Owner")
    with sessions() as db:
        db.get(CustomerModel, "919999999991").auth_version = 2
        db.commit()
    assert rpc(client, "tools/list").status_code == 401


def test_untrusted_host_and_origin_rejected(mcp_client):
    client, _ = mcp_client
    assert rpc(client, "tools/list").headers["Cache-Control"] == "no-store"
    client.headers["Host"] = "evil.example"
    assert rpc(client, "tools/list").status_code == 421
    client.headers["Host"] = "testserver"
    client.headers["Origin"] = "https://evil.example"
    assert rpc(client, "tools/list").status_code == 403


def test_mcp_rate_limit_and_production_configuration(monkeypatch):
    assert rule_for("/mcp/") == (30, 60)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("MCP_ENABLED", "true")
    monkeypatch.delenv("MCP_ALLOWED_HOSTS", raising=False)
    with pytest.raises(RuntimeError, match="MCP_ALLOWED_HOSTS"):
        build_mcp()
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "*")
    with pytest.raises(RuntimeError, match="exact hostnames"):
        build_mcp()


def test_backend_failures_do_not_leak_database_details(mcp_client):
    from sqlalchemy.exc import OperationalError
    client, _ = mcp_client
    failure = OperationalError("SELECT secret", {"customer": "PRIVATE"}, Exception("PRIVATE DB HOST"))
    with patch("app.mcp_server.get_customer_order", side_effect=failure):
        result = call(client, "get_my_order_status", {"order_id": 101})
    assert result["isError"]
    assert "PRIVATE" not in json.dumps(result)
    assert "temporarily unavailable" in json.dumps(result)
