import os
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite:///./test_mobile_ai_api.db"
os.environ["JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app
from app.customer_api import _mobile_ai_reply
from app.db import SessionLocal
from app.models import OrderModel, ProductModel
from app.state import get_state

Base.metadata.create_all(bind=engine)
client = TestClient(app)


def auth():
    payload = {"phone": "8888888888", "name": "AI Test User", "pin": "123456", "device_id": "test-device-8888888888"}
    registered = client.post("/auth/register", json=payload)
    if registered.status_code == 409:
        logged_in = client.post("/auth/login", json=payload)
        assert logged_in.status_code == 200
        return logged_in.json()["access_token"]
    assert registered.status_code == 200
    return registered.json()["access_token"]


class MobileAiApiTests(unittest.TestCase):
    def test_requires_authentication(self):
        response = client.post("/customers/me/ai/chat", json={"message": "What vegetables are available?"})
        self.assertEqual(response.status_code, 401)

    def test_returns_advisory_reply_without_commerce_authority(self):
        token = auth()
        headers = {"Authorization": f"Bearer {token}"}
        with patch("app.customer_api._mobile_ai_reply", return_value="Please check the Products screen for live prices and stock.") as reply:
            response = client.post("/customers/me/ai/chat", headers=headers, json={"message": "How much are tomatoes?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply"], "Please check the Products screen for live prices and stock.")
        reply.assert_called_once_with("How much are tomatoes?", "8888888888")


    def test_product_price_and_stock_answers_use_live_catalog(self):
        db = SessionLocal()
        product = ProductModel(
            name="Tomatoes",
            unit="1 kg",
            category="Vegetables",
            price=42.5,
            in_stock=True,
            stock_quantity=10,
        )
        db.add(product)
        db.commit()
        try:
            reply = _mobile_ai_reply("How much are tomatoes?", "8888888888")
            self.assertIn("Tomatoes", reply)
            self.assertIn("₹42.50", reply)
            self.assertIn("In stock", reply)
        finally:
            db.delete(product)
            db.commit()
            db.close()

    def test_unknown_product_gives_catalog_guidance(self):
        with patch("app.openai_service.generate_mobile_reply") as fallback:
            reply = _mobile_ai_reply("How much is dragonfruit?", "8888888888")
        self.assertIn("couldn't find that item", reply)
        fallback.assert_not_called()

    def test_order_number_and_tracking_use_customer_order(self):
        token = auth()
        db = SessionLocal()
        order = OrderModel(customer_id="8888888888", status="OUT_FOR_DELIVERY", total=349.0, address="Talegaon, Pune, 410507", payment_method="COD")
        db.add(order)
        db.commit()
        db.refresh(order)
        order_id = order.id
        db.close()
        try:
            with patch("app.openai_service.generate_mobile_reply") as fallback:
                number_reply = _mobile_ai_reply("What is my order number?", "8888888888")
                status_reply = _mobile_ai_reply(f"Track order {order_id}", "8888888888")
            self.assertIn(f"Order #{order_id}", number_reply)
            self.assertIn("Out For Delivery", number_reply)
            self.assertIn(f"Order #{order_id}", status_reply)
            self.assertIn("Out For Delivery", status_reply)
            fallback.assert_not_called()
        finally:
            db = SessionLocal()
            row = db.get(OrderModel, order_id)
            if row:
                db.delete(row)
                db.commit()
            db.close()

    def test_order_status_query_uses_authoritative_customer_order(self):
        token = auth()
        headers = {"Authorization": f"Bearer {token}"}
        with patch("app.customer_api._mobile_ai_reply", return_value="authoritative") as reply:
            response = client.post("/customers/me/ai/chat", headers=headers, json={"message": "What is my order number?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply"], "authoritative")
        reply.assert_called_once_with("What is my order number?", "8888888888")

    def test_tracking_follow_up_order_id_uses_persistent_state(self):
        db = SessionLocal()
        order = OrderModel(
            customer_id="8888888888",
            status="OUT_FOR_DELIVERY",
            total=275.0,
            address="Talegaon, Pune, 410507",
            payment_method="COD",
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        order_id = order.id
        db.close()
        try:
            first = _mobile_ai_reply("Track my order", "8888888888")
            self.assertIn("Please share the Order ID", first)
            self.assertTrue(get_state("8888888888").status_order_lookup)

            with patch("app.openai_service.generate_mobile_reply") as fallback:
                second = _mobile_ai_reply(str(order_id), "8888888888")

            self.assertIn(f"Order #{order_id}", second)
            self.assertIn("Out For Delivery", second)
            self.assertFalse(get_state("8888888888").status_order_lookup)
            fallback.assert_not_called()
        finally:
            db = SessionLocal()
            row = db.get(OrderModel, order_id)
            if row:
                db.delete(row)
                db.commit()
            db.close()


if __name__ == "__main__":
    unittest.main()
