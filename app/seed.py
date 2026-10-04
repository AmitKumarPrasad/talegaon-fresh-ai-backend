import json
from pathlib import Path

from sqlalchemy import func

from app.catalog import PRODUCTS
from app.db import SessionLocal
from app.models import ProductModel

# Online retail benchmarks checked 2026-10-02; not live Talegaon prices.
CATALOG_REFERENCES = json.loads(
    Path(__file__).with_name("catalog_references.json").read_text()
)
SEED_PRICES = {'Tomato': 40, 'Potato': 60, 'Onion': 40, 'Carrot': 50, 'Capsicum': 70, 'Cabbage': 30, 'Cauliflower': 40, 'Ladyfinger': 60, 'Green Beans': 80, 'Spinach': 30, 'Coriander': 20, 'Green Chilli': 30, 'Ginger': 40, 'Garlic': 50, 'Cut Potato': 45, 'Cut Onion': 45, 'Cut Carrot': 35, 'Cut Green Beans': 45, 'Cut Cabbage': 40, 'Cut Cauliflower': 50, 'Cut Mixed Vegetables': 70, 'Cut Bottle Gourd': 40, 'Banana': 90, 'Apple': 220, 'Orange': 90, 'Grapes': 100, 'Pomegranate': 140, 'Papaya': 60}
SEED_PRICES.update({item["name"]: item["price"] for item in CATALOG_REFERENCES})
# Sugar uses bb Popular as a price benchmark only, not a branded product photo.
SEED_IMAGES = {item["name"]: item["image_url"] for item in CATALOG_REFERENCES
               if item["name"] != "Sugar"}
SEED_DATA = {product.name: {"price": SEED_PRICES[product.name],
                           "image_url": SEED_IMAGES.get(product.name)}
             for product in PRODUCTS}


def is_legacy_catalog_image(url: str | None) -> bool:
    return bool(url and url.startswith("https://images.bigbasket.com/p/")
                and url.endswith("/260x260-c0bab6ba.jpg"))


def seed_products() -> None:
    db = SessionLocal()
    try:
        for product in PRODUCTS:
            row = db.query(ProductModel).filter(
                func.lower(ProductModel.name) == product.name.lower()
            ).first()
            image = SEED_IMAGES.get(product.name)
            if row is None:
                # Let the database allocate IDs; catalog menu IDs aren't DB IDs.
                db.add(ProductModel(
                    name=product.name, unit=product.unit, category=product.category,
                    price=SEED_PRICES[product.name], in_stock=True,
                    stock_quantity=100, image_url=image,
                ))
            else:
                if row.category == "Other":
                    row.category = product.category
                # Existing units, prices, stock and custom photos are admin-owned.
                if not row.image_url or is_legacy_catalog_image(row.image_url):
                    row.image_url = image
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_products()
