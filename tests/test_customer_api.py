import sys
from itertools import count
from unittest.mock import patch
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal
from app.main import app
from app.models import OrderModel, OrderStatusHistoryModel, ProductModel

client = TestClient(app)
_phones = count(9999999999, -1)


def auth():
    registered = client.post("/auth/register", json={
        "phone": str(next(_phones)), "name": "Test User", "pin": "123456",
        "device_id": "customer-api-test-device",
    })
    assert registered.status_code == 200
    return registered.json()["access_token"]


@pytest.fixture(autouse=True)
def isolated_customer_database(monkeypatch):
    global _phones
    _phones = count(9999999999, -1)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)
    for name, module in list(sys.modules.items()):
        if name.startswith("app.") and getattr(module, "SessionLocal", None) is SessionLocal:
            monkeypatch.setattr(module, "SessionLocal", factory)
    monkeypatch.setenv("JWT_SECRET", "customer-api-test-secret")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setattr("app.customer_api.notify_seller", lambda *args, **kwargs: None)
    with factory() as db:
        db.add(ProductModel(name="Tomato", unit="1 kg", price=40, in_stock=True, stock_quantity=10))
        db.commit()
    yield
    engine.dispose()


def test_auth_and_addresses():
    token = auth()
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post("/customers/me/addresses", headers=headers, json={
        "label": "Home", "address": "Main Road", "city": "Talegaon", "pincode": "410507", "is_default": True
    })
    assert created.status_code == 200
    address_id = created.json()["address"]["id"]
    listed = client.get("/customers/me/addresses", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["addresses"][0]["label"] == "Home"
    deleted = client.delete(f"/customers/me/addresses/{address_id}", headers=headers)
    assert deleted.status_code == 200


def test_address_update_reassigns_default_and_blocks_other_customer():
    token = auth()
    headers = {"Authorization": f"Bearer {token}"}
    first = client.post("/customers/me/addresses", headers=headers, json={
        "label": "Home", "address": "Main Road", "city": "Talegaon",
        "pincode": "410507", "is_default": True
    })
    assert first.status_code == 200
    first_id = first.json()["address"]["id"]

    second = client.post("/customers/me/addresses", headers=headers, json={
        "label": "Office", "address": "Market Road", "city": "Talegaon",
        "pincode": "410507", "is_default": False
    })
    assert second.status_code == 200
    second_id = second.json()["address"]["id"]

    updated = client.put(
        f"/customers/me/addresses/{second_id}",
        headers=headers,
        json={
            "label": "Office", "address": "Market Road", "city": "Talegaon",
            "pincode": "410507", "is_default": True
        },
    )
    assert updated.status_code == 200
    assert updated.json()["address"]["is_default"] is True

    listed = client.get("/customers/me/addresses", headers=headers)
    assert listed.status_code == 200
    rows = {row["id"]: row for row in listed.json()["addresses"]}
    assert rows[first_id]["is_default"] is False
    assert rows[second_id]["is_default"] is True

    other_token = auth()
    other_headers = {"Authorization": f"Bearer {other_token}"}
    forbidden = client.put(
        f"/customers/me/addresses/{second_id}",
        headers=other_headers,
        json={
            "label": "Other", "address": "Other Road", "city": "Talegaon",
            "pincode": "410507", "is_default": True
        },
    )
    assert forbidden.status_code == 404


def test_cart_and_orders():
    token = auth()
    headers = {"Authorization": f"Bearer {token}"}
    cart = client.put("/customers/me/cart", headers=headers, json={
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 40, "quantity": 2}]
    })
    assert cart.status_code == 200
    assert cart.json()["items"][0]["quantity"] == 2

    order = client.post("/customers/me/orders", headers=headers, json={
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 999, "quantity": 2}],
        "address": "Main Road, Talegaon, 410507",
        "payment_method": "COD"
    })
    assert order.status_code == 200
    assert order.json()["subtotal"] == 80
    assert order.json()["delivery_fee"] == 20
    assert order.json()["total"] == 100
    assert order.json()["status"] == "CONFIRMED"
    assert isinstance(order.json()["created_at"], str)
    created_at = datetime.fromisoformat(order.json()["created_at"])
    assert created_at.tzinfo is not None

    orders = client.get("/customers/me/orders", headers=headers)
    assert orders.status_code == 200
    assert orders.json()["orders"][0]["order_id"] == order.json()["order_id"]



def test_checkout_records_payment_status_transition_history():
    from app.db import SessionLocal

    token = auth()
    headers = {"Authorization": f"Bearer {token}"}
    order = client.post("/customers/me/orders", headers=headers, json={
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 999, "quantity": 1}],
        "address": "Main Road, Talegaon, 410507",
        "payment_method": "COD"
    })
    assert order.status_code == 200
    order_id = order.json()["order_id"]

    db = SessionLocal()
    history = (
        db.query(OrderStatusHistoryModel)
        .filter(OrderStatusHistoryModel.order_id == order_id)
        .order_by(OrderStatusHistoryModel.id)
        .all()
    )
    assert [(row.from_status, row.to_status) for row in history] == [("PENDING", "CONFIRMED")]
    db.close()


def test_upi_checkout_records_payment_pending_transition_history():
    from app.db import SessionLocal

    _reset_tomato_stock()
    token = auth()
    headers = {"Authorization": f"Bearer {token}"}
    order = client.post("/customers/me/orders", headers=headers, json={
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 999, "quantity": 1}],
        "address": "Main Road, Talegaon, 410507",
        "payment_method": "UPI"
    })
    assert order.status_code == 200
    order_id = order.json()["order_id"]

    db = SessionLocal()
    history = db.query(OrderStatusHistoryModel).filter(OrderStatusHistoryModel.order_id == order_id).all()
    assert [(row.from_status, row.to_status) for row in history] == [("PENDING", "PAYMENT_PENDING")]
    db.close()


def test_customer_upi_payment_link_is_created_and_reused():
    from unittest.mock import patch

    _reset_tomato_stock()
    token = auth()
    headers = {"Authorization": f"Bearer {token}"}
    order = client.post("/customers/me/orders", headers=headers, json={
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 999, "quantity": 1}],
        "address": "Main Road, Talegaon, 410507",
        "payment_method": "UPI"
    })
    assert order.status_code == 200
    order_id = order.json()["order_id"]
    assert order.json()["status"] == "PAYMENT_PENDING"

    with patch("app.customer_api.create_payment_link") as create_link:
        create_link.return_value = {"id": "plink_customer_123", "short_url": "https://rzp.io/i/customer-test"}
        first = client.post(f"/customers/me/orders/{order_id}/payment-link", headers=headers)
        assert first.status_code == 200
        assert first.json()["payment_link_url"] == "https://rzp.io/i/customer-test"
        assert "razorpay_payment_link_id" not in first.json()
        with SessionLocal() as db:
            saved_order = db.get(OrderModel, order_id)
            assert saved_order.razorpay_payment_link_id == "plink_customer_123"
            assert saved_order.payment_link_url == "https://rzp.io/i/customer-test"
        create_link.assert_called_once_with(order_id, 60.0, "9999999999")

        second = client.post(f"/customers/me/orders/{order_id}/payment-link", headers=headers)
        assert second.status_code == 200
        assert second.json()["payment_link_url"] == "https://rzp.io/i/customer-test"
        assert create_link.call_count == 1


def test_customer_upi_payment_link_requires_upi_order():
    token = auth()
    headers = {"Authorization": f"Bearer {token}"}
    order = client.post("/customers/me/orders", headers=headers, json={
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 40, "quantity": 1}],
        "address": "Main Road, Talegaon, 410507",
        "payment_method": "COD"
    })
    assert order.status_code == 200
    response = client.post(f"/customers/me/orders/{order.json()['order_id']}/payment-link", headers=headers)
    assert response.status_code == 400


def test_customer_shop200_quote_and_order_use_catalog_prices_and_delivery_fee():
    token = auth()
    headers = {"Authorization": "Bearer " + token}
    items = [{"name": "Tomato", "unit": "1 kg", "price": 999, "quantity": 5}]

    quote = client.post(
        "/customers/me/promos/validate",
        headers=headers,
        json={"promo_code": "shop200", "items": items},
    )

    assert quote.status_code == 200
    assert quote.json() == {
        "promo_code": "SHOP200",
        "subtotal": 200.0,
        "delivery_fee": 0.0,
        "discount_amount": 20.0,
        "total": 180.0,
    }

    order = client.post("/customers/me/orders", headers=headers, json={
        "items": items,
        "address": "Main Road, Talegaon, 410507",
        "payment_method": "COD",
        "promo_code": "SHOP200",
    })
    assert order.status_code == 200
    assert order.json()["promo_code"] == "SHOP200"
    assert order.json()["discount_amount"] == 20
    assert order.json()["delivery_fee"] == 0
    assert order.json()["total"] == 180


def test_shop200_promo_requires_200_and_returns_flat_discount():
    headers = {"Authorization": "Bearer " + auth()}
    below = client.post("/customers/me/promos/validate", headers=headers, json={
        "promo_code": "SHOP200",
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 40, "quantity": 4}],
    })
    assert below.status_code == 400
    assert "₹200" in below.json()["detail"]

    eligible = client.post("/customers/me/promos/validate", headers=headers, json={
        "promo_code": " shop200 ",
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 40, "quantity": 5}],
    })
    assert eligible.status_code == 200
    assert eligible.json()["promo_code"] == "SHOP200"
    assert eligible.json()["subtotal"] == 200
    assert eligible.json()["discount_amount"] == 20


def test_customer_promo_rules_keep_configured_caps_and_minimums():
    headers = {"Authorization": "Bearer " + auth()}
    welcome = client.post("/customers/me/promos/validate", headers=headers, json={
        "promo_code": "WELCOME50",
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 40, "quantity": 13}],
    })
    assert welcome.status_code == 200
    assert welcome.json()["subtotal"] == 520
    assert welcome.json()["discount_amount"] == 50
    assert welcome.json()["delivery_fee"] == 0
    assert welcome.json()["total"] == 470

    capped = client.post("/customers/me/promos/validate", headers=headers, json={
        "promo_code": "FRESHORA20",
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 40, "quantity": 13}],
    })
    assert capped.status_code == 200
    assert capped.json()["subtotal"] == 520
    assert capped.json()["discount_amount"] == 100
    assert capped.json()["total"] == 420

    below_minimum = client.post(
        "/customers/me/promos/validate",
        headers=headers,
        json={
            "promo_code": "WELCOME50",
            "items": [{"name": "Tomato", "unit": "1 kg", "price": 40, "quantity": 4}],
        },
    )
    assert below_minimum.status_code == 400


def test_delivery_fee_is_free_at_and_above_199():
    first_headers = {"Authorization": "Bearer " + auth()}
    below = client.post("/customers/me/orders", headers=first_headers, json={
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 40, "quantity": 4}],
        "address": "Main Road, Talegaon, 410507",
        "payment_method": "COD",
    })
    assert below.status_code == 200
    assert below.json()["total"] == 180
    assert below.json()["delivery_fee"] == 20

    second_headers = {"Authorization": "Bearer " + auth()}
    at_threshold = client.post("/customers/me/orders", headers=second_headers, json={
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 40, "quantity": 5}],
        "address": "Main Road, Talegaon, 410507",
        "payment_method": "COD",
    })
    assert at_threshold.status_code == 200
    assert at_threshold.json()["total"] == 200
    assert at_threshold.json()["delivery_fee"] == 0


def test_referral_code_discount_is_first_order_only_and_owner_cannot_redeem():
    owner_headers = {"Authorization": "Bearer " + auth()}
    code_response = client.get(
        "/customers/me/referral-code",
        headers=owner_headers,
    )
    assert code_response.status_code == 200
    code = code_response.json()["referral_code"]
    assert code.startswith("FRESHORA")
    assert len(code) == len("FRESHORA") + 8
    assert client.get(
        "/customers/me/referral-code",
        headers=owner_headers,
    ).json()["referral_code"] == code

    self_redeem = client.post(
        "/customers/me/promos/validate",
        headers=owner_headers,
        json={
            "promo_code": code,
            "items": [{"name": "Tomato", "unit": "1 kg", "price": 40, "quantity": 10}],
        },
    )
    assert self_redeem.status_code == 400

    invitee_headers = {"Authorization": "Bearer " + auth()}
    from app.db import SessionLocal
    db = SessionLocal()
    tomato = db.query(ProductModel).filter_by(name="Tomato").one()
    tomato.price = 50
    tomato.stock_quantity = 20
    tomato.in_stock = True
    db.commit()
    db.close()

    payload = {
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 50, "quantity": 10}],
        "address": "Main Road, Talegaon, 410507",
        "payment_method": "COD",
        "promo_code": code,
    }
    order = client.post("/customers/me/orders", headers=invitee_headers, json=payload)
    assert order.status_code == 200
    assert order.json()["discount_amount"] == 100
    assert order.json()["delivery_fee"] == 0
    assert order.json()["total"] == 400

    repeated = client.post("/customers/me/promos/validate", headers=invitee_headers, json={
        "promo_code": code,
        "items": payload["items"],
    })
    assert repeated.status_code == 400


def test_unauthorized_customer_api():
    response = client.get("/customers/me/cart")
    assert response.status_code == 401


def test_registration_rejects_duplicate_account():
    auth()
    duplicate = client.post("/auth/register", json={
        "phone": "9999999999", "pin": "123456", "device_id": "customer-api-test-device",
    })
    assert duplicate.status_code == 409


def test_pin_invalid_attempt_lockout():
    auth()
    payload = {"phone": "9999999999", "pin": "000000", "device_id": "customer-api-test-device"}
    for _ in range(4):
        response = client.post("/auth/login", json=payload)
        assert response.status_code == 401
    locked = client.post("/auth/login", json=payload)
    assert locked.status_code == 429
    payload["pin"] = "123456"
    assert client.post("/auth/login", json=payload).status_code == 429


def test_logout_revokes_existing_token():
    token = auth()
    headers = {"Authorization": f"Bearer {token}"}
    before = client.get("/customers/me", headers=headers)
    assert before.status_code == 200
    logged_out = client.post("/auth/logout", headers=headers)
    assert logged_out.status_code == 200
    revoked = client.get("/customers/me", headers=headers)
    assert revoked.status_code == 401


def test_customer_order_tracking_is_scoped_to_customer():
    token = auth()
    headers = {"Authorization": f"Bearer {token}"}
    order = client.post("/customers/me/orders", headers=headers, json={
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 999, "quantity": 1}],
        "address": "Main Road, Talegaon, 410507",
        "payment_method": "COD"
    })
    assert order.status_code == 200
    order_id = order.json()["order_id"]
    details = client.get(f"/customers/me/orders/{order_id}", headers=headers)
    assert details.status_code == 200
    assert details.json()["order_id"] == order_id
    assert details.json()["status"] == "CONFIRMED"
    assert "PACKING" in details.json()["allowed_next_statuses"]
    missing = client.get("/customers/me/orders/999999", headers=headers)
    assert missing.status_code == 404

def _reset_tomato_stock(quantity=10):
    from app.db import SessionLocal
    db = SessionLocal()
    product = db.query(ProductModel).filter_by(name="Tomato").one()
    product.stock_quantity = quantity
    product.in_stock = quantity > 0
    db.commit()
    db.close()


def test_order_reserves_stock_and_rejects_insufficient_quantity():
    _reset_tomato_stock()
    token = auth()
    headers = {"Authorization": f"Bearer {token}"}
    first = client.post("/customers/me/orders", headers=headers, json={
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 40, "quantity": 6}],
        "address": "Main Road, Talegaon, 410507", "payment_method": "COD"
    })
    assert first.status_code == 200
    from app.db import SessionLocal
    db = SessionLocal()
    product = db.query(ProductModel).filter_by(name="Tomato").one()
    assert product.stock_quantity == 4
    assert product.in_stock is True
    db.close()
    second = client.post("/customers/me/orders", headers=headers, json={
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 40, "quantity": 5}],
        "address": "Main Road, Talegaon, 410507", "payment_method": "COD"
    })
    assert second.status_code == 409
    db = SessionLocal()
    product = db.query(ProductModel).filter_by(name="Tomato").one()
    assert product.stock_quantity == 4
    db.close()


def test_order_consumes_exact_remaining_stock_and_marks_product_out_of_stock():
    _reset_tomato_stock(4)
    token = auth()
    headers = {"Authorization": f"Bearer {token}"}
    order = client.post("/customers/me/orders", headers=headers, json={
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 40, "quantity": 4}],
        "address": "Main Road, Talegaon, 410507", "payment_method": "COD"
    })
    assert order.status_code == 200
    from app.db import SessionLocal
    db = SessionLocal()
    product = db.query(ProductModel).filter_by(name="Tomato").one()
    assert product.stock_quantity == 0
    assert product.in_stock is False
    db.close()


def test_failed_order_rolls_back_stock_reservation():
    _reset_tomato_stock()
    token = auth()
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/customers/me/orders", headers=headers, json={
        "items": [
            {"name": "Tomato", "unit": "1 kg", "price": 40, "quantity": 2},
            {"name": "Missing Product", "unit": "1 kg", "price": 10, "quantity": 1},
        ],
        "address": "Main Road, Talegaon, 410507", "payment_method": "COD"
    })
    assert response.status_code == 400
    from app.db import SessionLocal
    db = SessionLocal()
    product = db.query(ProductModel).filter_by(name="Tomato").one()
    assert product.stock_quantity == 10
    assert product.in_stock is True
    db.close()



def test_checkout_notifies_seller_after_order_commit():
    token = auth()
    headers = {"Authorization": f"Bearer {token}"}
    from app.db import SessionLocal
    db = SessionLocal()
    product = ProductModel(
        name="Notification Test Tomato",
        unit="1 kg",
        price=50.0,
        in_stock=True,
        stock_quantity=20,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    product_id = product.id
    db.close()

    payload = {
        "items": [{"name": "Notification Test Tomato", "unit": "1 kg", "price": 50.0, "quantity": 2}],
        "address": "Talegaon, Pune, 410507",
        "payment_method": "COD",
    }

    body = None
    try:
        with patch("app.customer_api.notify_seller", return_value={"status": "sent"}) as notify:
            response = client.post("/customers/me/orders", headers=headers, json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "CONFIRMED"
        assert body["delivery_fee"] == 20.0
        assert body["total"] == 120.0
        notify.assert_called_once()
        call = notify.call_args.kwargs
        assert call["order_id"] == body["order_id"]
        assert call["total"] == 120.0
        assert call["payment_method"] == "COD"

        db = SessionLocal()
        created = db.get(OrderModel, body["order_id"])
        assert created is not None
        assert created.status == "CONFIRMED"
        assert created.delivery_fee == 20.0
        assert created.total == 120.0
        db.close()
    finally:
        db = SessionLocal()
        if body is not None and body.get("order_id") is not None:
            created = db.get(OrderModel, body["order_id"])
            if created:
                db.delete(created)
        test_product = db.get(ProductModel, product_id)
        if test_product:
            db.delete(test_product)
        db.commit()
        db.close()


def test_ai_order_number_query_returns_latest_order_without_llm():
    from unittest.mock import patch

    token = auth()
    headers = {"Authorization": f"Bearer {token}"}
    _reset_tomato_stock()
    order = client.post("/customers/me/orders", headers=headers, json={
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 40, "quantity": 1}],
        "address": "Main Road, Talegaon, 410507",
        "payment_method": "COD",
    })
    assert order.status_code == 200
    order_id = order.json()["order_id"]

    with patch("app.openai_service.generate_mobile_reply") as generate:
        response = client.post(
            "/customers/me/ai/chat",
            headers=headers,
            json={"message": "What is my latest order number?"},
        )

    assert response.status_code == 200
    assert f"Order #{order_id}" in response.json()["reply"]
    generate.assert_not_called()


def test_ai_specific_order_status_does_not_leak_other_customer_order():
    from unittest.mock import patch

    token = auth()
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.openai_service.generate_mobile_reply") as generate:
        response = client.post(
            "/customers/me/ai/chat",
            headers=headers,
            json={"message": "What is the status of order 999999?"},
        )

    assert response.status_code == 200
    assert "couldn't find that order under your account" in response.json()["reply"].lower()
    generate.assert_not_called()


def test_ai_order_status_language_does_not_fall_back_to_llm():
    from unittest.mock import patch

    token = auth()
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.openai_service.generate_mobile_reply") as generate:
        response = client.post(
            "/customers/me/ai/chat",
            headers=headers,
            json={"message": "Can you check my order?"},
        )

    assert response.status_code == 200
    reply = response.json()["reply"].lower()
    assert "order" in reply
    assert "order id" in reply or "my orders" in reply or "couldn't find" in reply
    generate.assert_not_called()


def test_ai_order_query_with_no_orders_gives_clear_next_step():
    from unittest.mock import patch

    token = auth()
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.openai_service.generate_mobile_reply") as generate:
        response = client.post(
            "/customers/me/ai/chat",
            headers=headers,
            json={"message": "Show my orders"},
        )

    assert response.status_code == 200
    assert "place an order first" in response.json()["reply"].lower()
    generate.assert_not_called()


def test_ai_tracking_without_order_number_asks_for_order_id():
    from unittest.mock import patch

    token = auth()
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.openai_service.generate_mobile_reply") as generate:
        response = client.post(
            "/customers/me/ai/chat",
            headers=headers,
            json={"message": "Track my order"},
        )

    assert response.status_code == 200
    reply = response.json()["reply"].lower()
    assert "order id" in reply
    assert "my orders" in reply
    generate.assert_not_called()


def test_ai_greeting_uses_deterministic_help_response():
    from unittest.mock import patch

    token = auth()
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.openai_service.generate_mobile_reply") as generate:
        response = client.post(
            "/customers/me/ai/chat",
            headers=headers,
            json={"message": "Hi"},
        )

    assert response.status_code == 200
    reply = response.json()["reply"]
    assert "FRESHORA" in reply
    assert "order status" in reply.lower()
    generate.assert_not_called()


def test_ai_help_request_uses_deterministic_help_response():
    from unittest.mock import patch

    token = auth()
    headers = {"Authorization": f"Bearer {token}"}

    with patch("app.openai_service.generate_mobile_reply") as generate:
        response = client.post(
            "/customers/me/ai/chat",
            headers=headers,
            json={"message": "What can you do?"},
        )

    assert response.status_code == 200
    assert "tracking" in response.json()["reply"].lower()
    generate.assert_not_called()


def test_new_order_alert_excludes_disabled_partners_and_customer_pii():
    from app.db import SessionLocal
    from app.models import DeliveryPartnerModel

    headers = {"Authorization": "Bearer " + auth()}
    with SessionLocal() as db:
        db.add_all([
            DeliveryPartnerModel(phone="9888888881", name="Active",
                                 pin_hash="unused-test-hash", active=True,
                                 fcm_token="active-partner-device-token"),
            DeliveryPartnerModel(phone="9888888882", name="Disabled",
                                 pin_hash="unused-test-hash", active=False,
                                 fcm_token="disabled-partner-device-token"),
            DeliveryPartnerModel(phone="9888888883", name="No push",
                                 pin_hash="unused-test-hash", active=True),
        ])
        db.commit()
    address = "Private Flat 23, Main Road, Talegaon, 410507"
    with patch(
        "app.notification_service.NotificationService.send_notification_to_partner",
        return_value=True,
    ) as send:
        response = client.post("/customers/me/orders", headers=headers, json={
            "items": [{"name": "Tomato", "unit": "1 kg", "price": 40, "quantity": 1}],
            "address": address,
            "payment_method": "COD",
        })
    assert response.status_code == 200
    send.assert_called_once()
    alert = send.call_args.kwargs
    assert alert["fcm_token"] == "active-partner-device-token"
    assert alert["body"] == "A new delivery order is available."
    assert "Test User" not in str(alert)
    assert address not in str(alert)
    assert alert["order_id"] == response.json()["order_id"]


@pytest.mark.parametrize("catalog_price,expected_status", [(498.99, 400), (499.0, 400), (500.0, 200)])
def test_welcome50_boundary_uses_server_prices_for_quote_and_checkout(catalog_price, expected_status):
    headers = {"Authorization": "Bearer " + auth()}
    from app.db import SessionLocal
    with SessionLocal() as db:
        product = db.query(ProductModel).filter_by(name="Tomato").one()
        product.price = catalog_price
        db.commit()
    # A forged client price must neither unlock the minimum nor change the charge.
    items = [{"name": "Tomato", "unit": "1 kg", "price": 9999, "quantity": 1}]
    quote = client.post("/customers/me/promos/validate", headers=headers, json={
        "promo_code": " welcome50 ", "items": items,
    })
    assert quote.status_code == expected_status
    checkout_payload = {
        "items": items, "promo_code": "WELCOME50",
        "address": "Main Road, Talegaon, 410507", "payment_method": "COD",
        "idempotency_key": "welcome50-first-checkout",
    }
    order = client.post("/customers/me/orders", headers=headers, json=checkout_payload)
    assert order.status_code == expected_status
    if expected_status == 200:
        assert quote.json()["subtotal"] == 500
        assert quote.json()["discount_amount"] == 50
        assert quote.json()["delivery_fee"] == 0
        assert quote.json()["total"] == 450
        assert order.json()["discount_amount"] == 50
        assert order.json()["delivery_fee"] == 0
        assert order.json()["total"] == 450
        replay = client.post("/customers/me/orders", headers=headers, json=checkout_payload)
        assert replay.status_code == 200
        assert replay.json() == order.json()
        # Actual first checkout consumes eligibility for any new checkout.
        assert client.post("/customers/me/promos/validate", headers=headers, json={
            "promo_code": "WELCOME50", "items": items,
        }).status_code == 400
        assert client.post("/customers/me/orders", headers=headers, json={
            "items": items, "promo_code": "WELCOME50",
            "address": "Main Road, Talegaon, 410507", "payment_method": "COD",
        }).status_code == 400
    with SessionLocal() as db:
        assert db.query(OrderModel).count() == (1 if expected_status == 200 else 0)
        product = db.query(ProductModel).filter_by(name="Tomato").one()
        assert product.stock_quantity == (9 if expected_status == 200 else 10)


@pytest.mark.parametrize("prior_status", ["CONFIRMED", "DELIVERED", "CANCELLED"])
def test_welcome50_rejects_any_existing_order_even_without_previous_discount(prior_status):
    headers = {"Authorization": "Bearer " + auth()}
    from app.db import SessionLocal
    from app.models import CustomerModel
    with SessionLocal() as db:
        customer = db.query(CustomerModel).one()
        db.add(OrderModel(customer_id=customer.phone, status=prior_status, total=40))
        product = db.query(ProductModel).filter_by(name="Tomato").one()
        product.price = 499
        db.commit()
    items = [{"name": "Tomato", "unit": "1 kg", "price": 499, "quantity": 1}]
    quote = client.post("/customers/me/promos/validate", headers=headers, json={
        "promo_code": "WELCOME50", "items": items,
    })
    assert quote.status_code == 400
    assert "first order" in quote.json()["detail"]
    checkout = client.post("/customers/me/orders", headers=headers, json={
        "items": items, "promo_code": "WELCOME50",
        "address": "Main Road, Talegaon, 410507", "payment_method": "COD",
    })
    assert checkout.status_code == 400
    with SessionLocal() as db:
        assert db.query(OrderModel).count() == 1
        assert db.query(ProductModel).filter_by(name="Tomato").one().stock_quantity == 10


def test_welcome50_cannot_be_stacked_by_combining_codes():
    headers = {"Authorization": "Bearer " + auth()}
    response = client.post("/customers/me/promos/validate", headers=headers, json={
        "promo_code": "WELCOME50,FRESH10",
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 40, "quantity": 13}],
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid promo code."

def test_customer_can_cancel_unpacked_order_and_stock_is_released():
    from app.db import SessionLocal

    token = auth()
    headers = {"Authorization": f"Bearer {token}"}
    order = client.post("/customers/me/orders", headers=headers, json={
        "items": [{"name": "Tomato", "unit": "1 kg", "price": 40, "quantity": 2}],
        "address": "Kothrud, Pune, 411038",
        "payment_method": "COD",
    })
    assert order.status_code == 200
    order_id = order.json()["order_id"]

    other_headers = {"Authorization": f"Bearer {auth()}"}
    assert client.post(
        f"/customers/me/orders/{order_id}/cancel", headers=other_headers
    ).status_code == 404

    cancelled = client.post(
        f"/customers/me/orders/{order_id}/cancel", headers=headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert client.post(
        f"/customers/me/orders/{order_id}/cancel", headers=headers
    ).status_code == 409

    with SessionLocal() as db:
        product = db.query(ProductModel).filter_by(name="Tomato").one()
        assert product.stock_quantity == 10
        history = (
            db.query(OrderStatusHistoryModel)
            .filter_by(order_id=order_id)
            .order_by(OrderStatusHistoryModel.id)
            .all()
        )
        assert [(row.from_status, row.to_status) for row in history] == [
            ("PENDING", "CONFIRMED"),
            ("CONFIRMED", "CANCELLED"),
        ]

