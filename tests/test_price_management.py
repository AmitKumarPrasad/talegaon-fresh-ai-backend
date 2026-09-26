import unittest
from unittest.mock import patch, MagicMock

from app.price_service import update_product_price


class ProductPriceManagementTests(unittest.TestCase):
    @patch("app.price_service.SessionLocal")
    def test_update_price_records_history(self, session_local):
        db = session_local.return_value
        product = type("Product", (), {
            "id": 1, "name": "Tomato", "unit": "1 kg",
            "price": 40.0, "in_stock": True,
        })()
        db.get.return_value = product
        result = update_product_price(1, 55.0, True)
        self.assertEqual(result["price"], 55.0)
        self.assertEqual(product.price, 55.0)
        db.add.assert_called_once()
        db.commit.assert_called_once()

    @patch("app.price_service.SessionLocal")
    def test_unknown_product(self, session_local):
        db = session_local.return_value
        db.get.return_value = None
        self.assertIsNone(update_product_price(999, 50.0))
        db.commit.assert_not_called()

    def test_rejects_non_positive_price(self):
        with self.assertRaises(ValueError):
            update_product_price(1, 0)


if __name__ == "__main__":
    unittest.main()
