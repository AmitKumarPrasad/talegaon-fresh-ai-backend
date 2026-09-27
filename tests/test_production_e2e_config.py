import os
import unittest

from app.config import validate_production_config


class ProductionE2EConfigTests(unittest.TestCase):
    def setUp(self):
        self.original = {key: os.environ.get(key) for key in (
            "ENVIRONMENT",
            "OPENAI_API_KEY",
            "WHATSAPP_VERIFY_TOKEN",
            "WHATSAPP_ACCESS_TOKEN",
            "WHATSAPP_PHONE_NUMBER_ID",
            "SELLER_WHATSAPP_NUMBER",
            "RAZORPAY_KEY_ID",
            "RAZORPAY_KEY_SECRET",
            "RAZORPAY_WEBHOOK_SECRET",
            "ADMIN_API_TOKEN",
            "DATABASE_URL",
        )}

    def tearDown(self):
        for key, value in self.original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_production_config_accepts_postgresql_and_required_integrations(self):
        os.environ["ENVIRONMENT"] = "production"
        os.environ["DATABASE_URL"] = "postgresql://user:password@db:5432/talegaon_fresh"
        for key in (
            "OPENAI_API_KEY",
            "WHATSAPP_VERIFY_TOKEN",
            "WHATSAPP_ACCESS_TOKEN",
            "WHATSAPP_PHONE_NUMBER_ID",
            "SELLER_WHATSAPP_NUMBER",
            "RAZORPAY_KEY_ID",
            "RAZORPAY_KEY_SECRET",
            "RAZORPAY_WEBHOOK_SECRET",
            "ADMIN_API_TOKEN",
        ):
            os.environ[key] = "configured"

        validate_production_config()

    def test_production_config_rejects_sqlite(self):
        os.environ["ENVIRONMENT"] = "production"
        os.environ["DATABASE_URL"] = "sqlite:///./test.db"
        for key in (
            "OPENAI_API_KEY",
            "WHATSAPP_VERIFY_TOKEN",
            "WHATSAPP_ACCESS_TOKEN",
            "WHATSAPP_PHONE_NUMBER_ID",
            "SELLER_WHATSAPP_NUMBER",
            "RAZORPAY_KEY_ID",
            "RAZORPAY_KEY_SECRET",
            "RAZORPAY_WEBHOOK_SECRET",
            "ADMIN_API_TOKEN",
        ):
            os.environ[key] = "configured"

        with self.assertRaisesRegex(RuntimeError, "SQLite"):
            validate_production_config()

    def test_production_config_rejects_non_postgresql_database(self):
        os.environ["ENVIRONMENT"] = "production"
        os.environ["DATABASE_URL"] = "mysql+pymysql://user:password@db:3306/talegaon_fresh"
        for key in (
            "OPENAI_API_KEY",
            "WHATSAPP_VERIFY_TOKEN",
            "WHATSAPP_ACCESS_TOKEN",
            "WHATSAPP_PHONE_NUMBER_ID",
            "SELLER_WHATSAPP_NUMBER",
            "RAZORPAY_KEY_ID",
            "RAZORPAY_KEY_SECRET",
            "RAZORPAY_WEBHOOK_SECRET",
            "ADMIN_API_TOKEN",
        ):
            os.environ[key] = "configured"

        with self.assertRaisesRegex(RuntimeError, "PostgreSQL"):
            validate_production_config()


if __name__ == "__main__":
    unittest.main()
