import os
import subprocess
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.seed import CATALOG_REFERENCES


def test_everyday_products_migrate_to_customer_api_without_overwriting_admin(tmp_path):
    url = f"sqlite:///{tmp_path / 'everyday.db'}"
    env = {**os.environ, "DATABASE_URL": url}
    def migrate(target):
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", target],
                       env=env, check=True, capture_output=True)

    migrate("0015")
    engine = create_engine(url)
    with engine.begin() as db:
        # A manually entered item already exists before the catalog expansion.
        # Its ID, case, pack size, selling price, sold-out stock and photo must survive.
        db.execute(text("INSERT INTO products "
                        "(id, name, unit, category, price, in_stock, stock_quantity, image_url) "
                        "VALUES (500, 'AMUL COW GHEE', '1 L', 'Specials', 700, 0, 0, "
                        "'https://example.com/admin-ghee.jpg')"))
    migrate("head")
    migrate("head")
    factory = sessionmaker(bind=engine)
    with patch("app.price_service.SessionLocal", factory):
        response = TestClient(app).get("/products")
    assert response.status_code == 200
    products = response.json()["products"]
    assert len(products) == 66
    by_name = {product["name"].lower(): product for product in products}
    ghee = by_name["amul cow ghee"]
    assert (ghee["id"], ghee["unit"], ghee["category"], ghee["price"], ghee["in_stock"]) == (
        500, "1 L", "Specials", 700, False)
    assert ghee["image_url"] == "https://example.com/admin-ghee.jpg"
    for reference in CATALOG_REFERENCES[-10:]:
        if reference["name"] == "Amul Cow Ghee":
            continue
        product = by_name[reference["name"].lower()]
        assert product["unit"] == reference["unit"]
        assert product["price"] == reference["price"]
        assert product["image_url"] == reference["image_url"]
    assert by_name["nescafe classic instant coffee powder"]["unit"] == "45 g"
    assert by_name["nescafe classic instant coffee powder"]["category"] == "Beverages"
    assert by_name["amul spiced buttermilk"]["category"] == "Dairy"
