import unittest
from unittest.mock import patch

from app.price_service import bulk_update_product_prices, update_product_price


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

    @patch("app.price_service.SessionLocal")
    def test_bulk_update_prices(self, session_local):
        db = session_local.return_value
        tomato = type("Product", (), {
            "id": 1, "name": "Tomato", "unit": "1 kg",
            "price": 40.0, "in_stock": True,
        })()
        potato = type("Product", (), {
            "id": 2, "name": "Potato", "unit": "1 kg",
            "price": 35.0, "in_stock": True,
        })()
        db.query.return_value.filter.return_value.all.return_value = [tomato, potato]

        result = bulk_update_product_prices([
            {"product_id": 1, "price": 45.0, "in_stock": True},
            {"product_id": 2, "price": 38.0, "in_stock": True},
        ])

        self.assertEqual([item["price"] for item in result], [45.0, 38.0])
        self.assertEqual(tomato.price, 45.0)
        self.assertEqual(potato.price, 38.0)
        self.assertEqual(db.add.call_count, 2)
        db.commit.assert_called_once()

    @patch("app.price_service.SessionLocal")
    def test_bulk_update_unknown_product(self, session_local):
        db = session_local.return_value
        db.query.return_value.filter.return_value.all.return_value = []
        with self.assertRaisesRegex(ValueError, "Product\(s\) not found"):
            bulk_update_product_prices([{"product_id": 999, "price": 50.0}])
        db.commit.assert_not_called()

    def test_rejects_non_positive_price(self):
        with self.assertRaises(ValueError):
            update_product_price(1, 0)

    def test_bulk_rejects_duplicate_product_ids(self):
        with self.assertRaisesRegex(ValueError, "Duplicate product IDs"):
            bulk_update_product_prices([
                {"product_id": 1, "price": 40.0},
                {"product_id": 1, "price": 45.0},
            ])


if __name__ == "__main__":
    unittest.main()
