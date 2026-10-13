import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from openai.types.responses.response_function_tool_call import ResponseFunctionToolCall
from openai.types.responses.response_reasoning_item import ResponseReasoningItem
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_token
from app.db import Base
from app.models import CustomerModel, OrderModel, ProductModel
from app.mcp_server import build_mcp
from app.mcp_chat import generate_mcp_reply, SAFE_REPLY, tool_output


@pytest.fixture
def backend(monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "testserver")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-unit-test-key")
    monkeypatch.setenv("ENVIRONMENT", "development")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        db.add_all([
            CustomerModel(phone="919999999981", name="Owner", auth_version=1),
            CustomerModel(phone="919999999982", name="Other", auth_version=1),
            ProductModel(name="Tomato", unit="kg", category="Vegetables", price=55, in_stock=True, stock_quantity=10),
            OrderModel(id=201, customer_id="919999999981", status="CONFIRMED", total=55, payment_method="COD", address="PRIVATE ADDRESS"),
        ])
        db.commit()
    server, transport = build_mcp()
    with patch("app.auth.SessionLocal", sessions), patch("app.mcp_server.SessionLocal", sessions), patch("app.order_details.SessionLocal", sessions):
        yield server, transport, sessions
    engine.dispose()


def tool_call(name, arguments, call_id="call_one"):
    return ResponseFunctionToolCall(type="function_call", name=name,
                                    arguments=json.dumps(arguments), call_id=call_id)


def response(output=None, text="", status="completed"):
    return SimpleNamespace(output=output or [], output_text=text, status=status)


def provider(*outputs):
    create = AsyncMock(side_effect=outputs)
    # Capture immutable inputs: the loop appends items to its local history.
    captured = []
    async def capture(**kwargs):
        captured.append(copy.deepcopy(kwargs))
        return await create(**kwargs)
    client = SimpleNamespace(responses=SimpleNamespace(create=capture))
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=client)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, create, captured


@pytest.mark.asyncio
async def test_real_mcp_catalog_and_stateless_reasoning_replay(backend):
    server, transport, _ = backend
    reasoning = ResponseReasoningItem(id="rs_test", type="reasoning", summary=[], encrypted_content="encrypted-test")
    factory, create, inputs = provider(
        response([reasoning, tool_call("search_products", {"query": "Tomato", "limit": 2})]),
        response(text="Tomato costs ₹55/kg."),
    )
    token = create_token("919999999981", "Owner")
    with patch("app.mcp_chat.AsyncOpenAI", factory):
        async with server.session_manager.run():
            reply = await generate_mcp_reply("Tomato ka price?", "Bearer " + token, transport)
    assert "55" in reply
    assert create.call_count == 2
    assert all(request["store"] is False for request in inputs)
    assert all(request["parallel_tool_calls"] is False for request in inputs)
    assert all("reasoning.encrypted_content" in request["include"] for request in inputs)
    assert inputs[1]["input"][1]["type"] == "reasoning"
    result = json.loads(inputs[1]["input"][-1]["output"])
    assert result["products"][0]["price"] == 55
    assert token not in json.dumps(inputs)
    assert "919999999981" not in json.dumps(inputs)


@pytest.mark.asyncio
async def test_other_customer_order_and_private_fields_not_sent(backend):
    server, transport, _ = backend
    factory, _, inputs = provider(
        response([tool_call("get_my_order_status", {"order_id": 201})]),
        response(text="Check the Order ID in My Orders."),
    )
    with patch("app.mcp_chat.AsyncOpenAI", factory):
        async with server.session_manager.run():
            await generate_mcp_reply("Order 201 status?", "Bearer " + create_token("919999999982", "Other"), transport)
    serialized = json.dumps(inputs)
    assert "PRIVATE ADDRESS" not in serialized
    assert "CONFIRMED" not in serialized
    assert "error" in inputs[1]["input"][-1]["output"]


@pytest.mark.asyncio
async def test_latest_order_lookup_is_grounded_and_redacted(backend):
    server, transport, _ = backend
    factory, _, inputs = provider(
        response([tool_call("get_my_order_status", {})]),
        response(text="Your latest order is #201, confirmed."),
    )
    with patch("app.mcp_chat.AsyncOpenAI", factory):
        async with server.session_manager.run():
            await generate_mcp_reply("Mera latest order?", "Bearer " + create_token("919999999981", "Owner"), transport)
    result = json.loads(inputs[1]["input"][-1]["output"])
    assert result["order_id"] == 201
    assert result["status"] == "CONFIRMED"
    assert "PRIVATE ADDRESS" not in json.dumps(inputs)


@pytest.mark.asyncio
async def test_revoked_token_never_calls_provider(backend):
    server, transport, sessions = backend
    token = create_token("919999999981", "Owner")
    with sessions() as db:
        db.get(CustomerModel, "919999999981").auth_version = 2
        db.commit()
    with patch("app.mcp_chat.AsyncOpenAI") as factory:
        async with server.session_manager.run():
            with pytest.raises(RuntimeError, match="temporarily unavailable"):
                await generate_mcp_reply("Order status", "Bearer " + token, transport)
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_tool_and_identity_injection_not_dispatched():
    session = SimpleNamespace(call_tool=AsyncMock())
    for call in (tool_call("cancel_order", {"order_id": 201}),
                 tool_call("get_my_order_status", {"order_id": 201, "customer_id": "other"}),
                 tool_call("search_products", ["not", "an", "object"])):
        assert "error" in await tool_output(session, call)
    session.call_tool.assert_not_called()


@pytest.mark.asyncio
async def test_model_loop_is_bounded(backend):
    server, transport, _ = backend
    factory, create, _ = provider(*[
        response([tool_call("search_products", {"query": "Tomato"}, f"call_{n}")])
        for n in range(3)
    ])
    with patch("app.mcp_chat.AsyncOpenAI", factory):
        async with server.session_manager.run():
            reply = await generate_mcp_reply("Tomato", "Bearer " + create_token("919999999981", "Owner"), transport)
    assert reply == SAFE_REPLY
    assert create.call_count == 3


@pytest.mark.asyncio
async def test_provider_failure_is_redacted_without_fallback(backend):
    server, transport, _ = backend
    factory, _, _ = provider(RuntimeError("PRIVATE PROVIDER DETAILS"))
    with patch("app.mcp_chat.AsyncOpenAI", factory), patch("app.openai_service.generate_mobile_reply") as fallback:
        async with server.session_manager.run():
            with pytest.raises(RuntimeError) as error:
                await generate_mcp_reply("Tomato", "Bearer " + create_token("919999999981", "Owner"), transport)
    assert "PRIVATE" not in str(error.value)
    fallback.assert_not_called()


def test_mobile_chat_uses_authenticated_header_and_safe_503(monkeypatch):
    from app.main import app
    from app.auth import current_customer
    transport = object()
    previous = app.state.customer_mcp_transport
    app.state.customer_mcp_transport = transport
    app.dependency_overrides[current_customer] = lambda: CustomerModel(phone="919999999981", name="Owner")
    try:
        with patch("app.mcp_chat.generate_mcp_reply", new_callable=AsyncMock, return_value="Live reply") as reply:
            result = TestClient(app).post("/customers/me/ai/chat", headers={"Authorization": "Bearer test-token"}, json={"message": "Tomato ka price?"})
        assert result.json() == {"reply": "Live reply"}
        reply.assert_awaited_once_with("Tomato ka price?", "Bearer test-token", transport)
        with patch("app.mcp_chat.generate_mcp_reply", new_callable=AsyncMock, side_effect=RuntimeError("PRIVATE")):
            result = TestClient(app).post("/customers/me/ai/chat", headers={"Authorization": "Bearer test-token"}, json={"message": "Hello"})
        assert result.status_code == 503
        assert "PRIVATE" not in result.text
    finally:
        app.state.customer_mcp_transport = previous
        app.dependency_overrides.pop(current_customer, None)
