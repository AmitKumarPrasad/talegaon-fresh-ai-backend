import os
import unittest
from unittest.mock import patch

from app.config import get_cors_allowed_origins, validate_production_config


class ProductionConfigTests(unittest.TestCase):
    def test_development_allows_missing_config(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=True):
            validate_production_config()

    def test_mobile_production_accepts_core_config_without_optional_integrations(self):
        env = {
            "ENVIRONMENT": "production",
            "ADMIN_API_TOKEN": "admin",
            "DATABASE_URL": "postgresql://user:pass@localhost/db",
            "JWT_SECRET": "configured-strong-secret-12345678901234567890",
        }
        with patch.dict(os.environ, env, clear=True):
            validate_production_config()

    def test_production_rejects_missing_jwt_secret(self):
        env = {
            "ENVIRONMENT": "production",
            "ADMIN_API_TOKEN": "admin",
            "DATABASE_URL": "postgresql://user:pass@localhost/db",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "JWT_SECRET"):
                validate_production_config()


    def test_production_cors_does_not_default_to_wildcard(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
            self.assertEqual(get_cors_allowed_origins(), [])

    def test_production_cors_rejects_wildcard(self):
        with patch.dict(
            os.environ,
            {"ENVIRONMENT": "production", "CORS_ALLOWED_ORIGINS": "*"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "CORS_ALLOWED_ORIGINS"):
                get_cors_allowed_origins()

    def test_production_requires_core_config(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
            with self.assertRaises(RuntimeError):
                validate_production_config()


if __name__ == "__main__":
    unittest.main()
