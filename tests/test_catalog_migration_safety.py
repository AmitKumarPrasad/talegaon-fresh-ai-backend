import os
import subprocess
import sys

from sqlalchemy import create_engine, text


def test_catalog_migration_preserves_existing_business_data(tmp_path):
    url = f"sqlite:///{tmp_path / 'catalog.db'}"
    env = {**os.environ, "DATABASE_URL": url}

    def migrate(target):
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", target],
                       env=env, check=True, capture_output=True)

    migrate("0014")
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(text("UPDATE products SET price=72, stock_quantity=0, in_stock=0, "
                        "image_url='https://example.com/butter.jpg' WHERE name='Amul Butter'"))
        db.execute(text("UPDATE products SET price=61, stock_quantity=7, "
                        "image_url='https://images.bigbasket.com/p/dairy/old/260x260-c0bab6ba.jpg' "
                        "WHERE name='Amul Taaza Milk'"))
    migrate("head")
    migrate("head")
    with engine.connect() as db:
        assert db.execute(text("SELECT count(*) FROM products")).scalar() == 44
        butter = db.execute(text("SELECT price, stock_quantity, in_stock, image_url "
                                 "FROM products WHERE name='Amul Butter'")).one()
        assert tuple(butter) == (72, 0, 0, "https://example.com/butter.jpg")
        milk = db.execute(text("SELECT price, stock_quantity, image_url FROM products "
                               "WHERE name='Amul Taaza Milk'")).one()
        assert tuple(milk[:2]) == (61, 7)
        assert milk.image_url.startswith("https://www.bbassets.com/")
        assert db.execute(text("SELECT category FROM products WHERE name='Tata Sampann Thick Poha'")).scalar() == "Bakery & Breakfast"
