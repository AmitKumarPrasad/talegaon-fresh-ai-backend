import unittest

from app.catalog import PRODUCTS
from app.seed import SEED_PRICES


class ExpandedCatalogTests(unittest.TestCase):
    def test_catalog_has_unique_ids_and_names(self):
        self.assertEqual(len(PRODUCTS), len({product.id for product in PRODUCTS}))
        self.assertEqual(
            len(PRODUCTS),
            len({product.name.lower() for product in PRODUCTS}),
        )

    def test_seed_prices_cover_every_baseline_product(self):
        self.assertEqual(
            {product.name for product in PRODUCTS},
            set(SEED_PRICES),
        )

    def test_daily_needs_categories_are_available(self):
        categories = {product.category for product in PRODUCTS}
        self.assertTrue(
            {
                "Vegetables",
                "Leafy Greens",
                "Fruits",
                "Dairy",
                "Grocery",
                "Snacks",
                "Masala & Spices",
                "Beverages",
                "Bakery & Breakfast",
                "Instant Food",
            }.issubset(categories)
        )

    def test_representative_market_products_have_expected_metadata(self):
        by_name = {product.name: product for product in PRODUCTS}
        self.assertEqual(by_name["Amul Taaza Milk"].unit, "1 L")
        self.assertEqual(by_name["Amul Taaza Milk"].category, "Dairy")
        self.assertEqual(SEED_PRICES["Amul Taaza Milk"], 59)

        self.assertEqual(by_name["Lay's Cream & Onion Chips"].category, "Snacks")
        self.assertEqual(SEED_PRICES["Lay's Cream & Onion Chips"], 20)

        self.assertEqual(
            by_name["Aashirvaad Whole Wheat Atta"].category,
            "Grocery",
        )
        self.assertEqual(SEED_PRICES["Aashirvaad Whole Wheat Atta"], 264)


if __name__ == "__main__":
    unittest.main()
