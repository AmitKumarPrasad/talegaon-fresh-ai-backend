from app.catalog import PRODUCTS
from app.db import SessionLocal
from app.models import ProductModel

# Baseline reference prices for initializing missing catalog items.
# Fresh produce and online retail prices vary by date/location; production admins
# remain responsible for current selling prices through the price-management APIs.
SEED_PRICES = {
    "Tomato": 40, "Potato": 35, "Onion": 40, "Carrot": 50,
    "Capsicum": 70, "Cabbage": 30, "Cauliflower": 40, "Ladyfinger": 60,
    "Green Beans": 80, "Spinach": 30, "Coriander": 20, "Green Chilli": 30,
    "Ginger": 40, "Garlic": 50, "Banana": 60, "Apple": 160,
    "Orange": 90, "Grapes": 100, "Pomegranate": 140, "Papaya": 60,
    "Amul Taaza Milk": 59, "Amul Masti Dahi": 50,
    "Amul Fresh Malai Paneer": 95, "Amul Butter": 63,
    "Amul Pure Milk Cheese Slices": 137,
    "Lay's Cream & Onion Chips": 20, "Bingo Tedhe Medhe": 14,
    "Parle Hide & Seek": 26, "Britannia Jim Jam": 35,
    "Chheda's Banana Chips": 70,
    "Aashirvaad Whole Wheat Atta": 264,
    "India Gate Rozana Basmati Rice": 454,
    "Tata Salt Iodised": 29, "Sugar": 69,
    "Tata Sampann Toor Dal": 174,
    "Fortune Sunlite Sunflower Oil": 177,
    "Maggi Masala Noodles": 60, "Tata Tea Gold": 264,
    "Harvest Gold Atta Bread": 65,
    "Catch Coriander Powder": 32,
}


def seed_products() -> None:
    db = SessionLocal()
    try:
        for product in PRODUCTS:
            row = db.query(ProductModel).filter_by(name=product.name).first()
            if row is None:
                db.add(
                    ProductModel(
                        name=product.name,
                        unit=product.unit,
                        category=product.category,
                        price=SEED_PRICES[product.name],
                        in_stock=True,
                        stock_quantity=100,
                    )
                )
            else:
                # Keep production price/stock authoritative while correcting
                # the stable catalog metadata.
                row.unit = product.unit
                row.category = product.category
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed_products()
