import os
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite:///./test_mobile_ai_api.db"
os.environ["JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app

Base.metadata.create_all(bind=engine)
client = TestClient(app)


def auth():
    requested = client.post("/auth/request-otp", json={"phone": "918888888888", "name": "AI Test User"})
    assert requested.status_code == 200
    otp = requested.json()["demo_otp"]
    verified = client.post("/auth/verify-otp", json={"phone": "918888888888", "otp": otp})
    assert verified.status_code == 200
    return verified.json()["token"]


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
        reply.assert_called_once_with("How much are tomatoes?")


if __name__ == "__main__":
    unittest.main()
