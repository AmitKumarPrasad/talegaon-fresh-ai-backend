import os
import unittest
from unittest.mock import patch
from app.config import validate_production_config

class ProductionConfigTests(unittest.TestCase):
    def test_development_allows_missing_config(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=True):
            validate_production_config()

    def test_production_rejects_missing_jwt_secret(self):
        env = {
            "ENVIRONMENT": "production",
            "OPENAI_API_KEY": "openai",
            "WHATSAPP_VERIFY_TOKEN": "verify",
            "WHATSAPP_ACCESS_TOKEN": "access",
            "WHATSAPP_PHONE_NUMBER_ID": "phone",
            "SELLER_WHATSAPP_NUMBER": "seller",
            "RAZORPAY_KEY_ID": "rzp",
            "RAZORPAY_KEY_SECRET": "secret",
            "RAZORPAY_WEBHOOK_SECRET": "webhook",
            "ADMIN_API_TOKEN": "admin",
            "DATABASE_URL": "postgresql://user:pass@localhost/db",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "JWT_SECRET"):
                validate_production_config()

    def test_production_requires_config(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
            with self.assertRaises(RuntimeError):
                validate_production_config()

if __name__ == "__main__":
    unittest.main()
