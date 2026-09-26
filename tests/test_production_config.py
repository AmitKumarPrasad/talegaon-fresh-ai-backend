import os
import unittest
from unittest.mock import patch
from app.config import validate_production_config

class ProductionConfigTests(unittest.TestCase):
    def test_development_allows_missing_config(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=True):
            validate_production_config()

    def test_production_requires_config(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
            with self.assertRaises(RuntimeError):
                validate_production_config()

if __name__ == "__main__":
    unittest.main()
