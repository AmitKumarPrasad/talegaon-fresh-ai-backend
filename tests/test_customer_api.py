import os
from datetime import datetime, timezone

os.environ["DATABASE_URL"] = "sqlite:///./test_customer_api.db"
os.environ["JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app
from app.models import ProductModel

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
    db.add(ProductModel(name="Tomato", unit="1 kg", price=40, in_stock=True))
    db.commit()
    db.close()


def test_auth_and_addresses():
    token = auth()
    headers = {"Authorization": f"Bearer {token}"}
    me = client.get("/customers/me", headers=headers)
    assert me.status_code == 200
    assert me.json() == {"phone": "919999999999", "name": "Test User"}
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

    orders = client.get("/customers/me/orders", headers=headers)
    assert orders.status_code == 200
    assert orders.json()["orders"][0]["order_id"] == order.json()["order_id"]


def test_unauthorized_customer_api():
    response = client.get("/customers/me/cart")
    assert response.status_code == 401
