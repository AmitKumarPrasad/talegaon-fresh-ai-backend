from app.catalog import PRODUCTS
from app.db import SessionLocal
from app.models import ProductModel

# Development seed values only. Replace with current business prices.
SEED_PRICES = {
    "Tomato": 40, "Potato": 35, "Onion": 40, "Carrot": 50,
    "Capsicum": 70, "Cabbage": 30, "Cauliflower": 40, "Ladyfinger": 60,
    "Green Beans": 80, "Spinach": 30, "Coriander": 20, "Green Chilli": 30,
    "Ginger": 40, "Garlic": 50, "Banana": 60, "Apple": 160,
    "Orange": 90, "Grapes": 100, "Pomegranate": 140, "Papaya": 60,
}

def seed_products() -> None:
    db = SessionLocal()
    try:
        for product in PRODUCTS:
            row = db.query(ProductModel).filter_by(name=product.name).first()
            if row is None:
                db.add(ProductModel(id=product.id, name=product.name, unit=product.unit,
                                    price=SEED_PRICES[product.name], in_stock=True, stock_quantity=100))
        db.commit()
    finally:
        db.close()

if __name__ == "__main__":
    seed_products()
