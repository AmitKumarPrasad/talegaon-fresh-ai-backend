from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.catalog import PRODUCTS
from app.db import Base
from app.models import ProductModel
from app.seed import seed_products, SEED_IMAGES


def test_seed_preserves_admin_values_and_is_idempotent():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add_all([
            ProductModel(id=150, name="Amul Butter", unit="custom pack",
                         category="Specials", price=72, stock_quantity=0,
                         in_stock=False, image_url="https://example.com/my-butter.jpg"),
            ProductModel(id=151, name="Amul Taaza Milk", unit="1 L", category="Other",
                         price=61, stock_quantity=7, in_stock=True,
                         image_url="https://images.bigbasket.com/p/dairy/40101-2_3-milk-cow-loose/260x260-c0bab6ba.jpg"),
        ])
        db.commit()
    with patch("app.seed.SessionLocal", factory):
        seed_products()
        seed_products()
    with factory() as db:
        assert db.query(ProductModel).count() == len(PRODUCTS)
        butter = db.get(ProductModel, 150)
        assert (butter.price, butter.stock_quantity, butter.in_stock) == (72, 0, False)
        assert (butter.unit, butter.category) == ("custom pack", "Specials")
        assert butter.image_url == "https://example.com/my-butter.jpg"
        milk = db.get(ProductModel, 151)
        assert (milk.price, milk.stock_quantity) == (61, 7)
        assert milk.category == "Dairy"
        assert milk.image_url == SEED_IMAGES["Amul Taaza Milk"]
        poha = db.query(ProductModel).filter_by(name="Tata Sampann Thick Poha").one()
        assert poha.id > 151
        assert poha.image_url == SEED_IMAGES[poha.name]
