import os
from datetime import datetime, timezone

os.environ["DATABASE_URL"] = "sqlite:///./test_customer_api.db"
os.environ["JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app
from app.models import OrderModel, ProductModel

Base.metadata.create_all(bind=engine)

client = TestClient(app)


def auth():
    requested = client.post("/auth/request-otp", json={"phone": "919999999999", "name": "Test User"})
    assert requested.status_code == 200
    otp = requested.json()["demo_otp"]
    verified = client.post("/auth/verify-otp", json={"phone": "919999999999", "otp": otp})
    assert verified.status_code == 200
    return verified.json()["token"]


def setup_module():
    from app.db import SessionLocal
    db = SessionLocal()
    db.query(ProductModel).delete()
    db.add(ProductModel(name="Tomato", unit="1 kg", price=40, in_stock=True, stock_quantity=10))
    db.commit()
    db.close()


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
    assert order.json()["total"] == 80
    assert order.json()["status"] == "CONFIRMED"
    assert isinstance(order.json()["created_at"], str)
    created_at = datetime.fromisoformat(order.json()["created_at"])
    assert created_at.tzinfo is not None

    orders = client.get("/customers/me/orders", headers=headers)
    assert orders.status_code == 200
    assert orders.json()["orders"][0]["order_id"] == order.json()["order_id"]



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
        assert first.json()["razorpay_payment_link_id"] == "plink_customer_123"
        create_link.assert_called_once_with(order_id, 40.0, "919999999999")

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


def test_unauthorized_customer_api():
    response = client.get("/customers/me/cart")
    assert response.status_code == 401


def test_otp_request_rate_limit():
    phone = "919999999998"
    for _ in range(3):
        response = client.post("/auth/request-otp", json={"phone": phone})
        assert response.status_code == 200
    limited = client.post("/auth/request-otp", json={"phone": phone})
    assert limited.status_code == 429


def test_otp_invalid_attempt_lockout():
    phone = "919999999997"
    requested = client.post("/auth/request-otp", json={"phone": phone})
    assert requested.status_code == 200
    for _ in range(4):
        response = client.post("/auth/verify-otp", json={"phone": phone, "otp": "000000"})
        assert response.status_code == 401
    locked = client.post("/auth/verify-otp", json={"phone": phone, "otp": "000000"})
    assert locked.status_code == 429
    requested_again = client.post("/auth/request-otp", json={"phone": phone})
    assert requested_again.status_code == 429


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
    _reset_tomato_stock()
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
        assert body["total"] == 100.0
        notify.assert_called_once()
        call = notify.call_args.kwargs
        assert call["order_id"] == body["id"]
        assert call["total"] == 100.0
        assert call["payment_method"] == "COD"

        db = SessionLocal()
        created = db.get(OrderModel, body["id"])
        assert created is not None
        assert created.status == "CONFIRMED"
        assert created.total == 100.0
        db.close()
    finally:
        db = SessionLocal()
        if body is not None and body.get("id") is not None:
            created = db.get(OrderModel, body["id"])
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
    assert "Talegaon Fresh" in reply
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
