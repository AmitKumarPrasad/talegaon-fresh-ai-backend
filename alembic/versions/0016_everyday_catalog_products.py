"""Add ten everyday staples, dairy and beverage products.

Price references were checked 2026-10-02. Existing selling prices and inventory
are retained. Freeze data here so future catalog changes cannot alter migrations.
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

CATALOG_ROWS = [('bb Royal Sooji Bombay Rava',
  '500 g',
  'Bakery & Breakfast',
  29,
  'https://www.bbassets.com/media/uploads/p/s/10000422_12-bb-royal-sooji-ordinarybombay-rava.jpg'),
 ('Tata Sampann Fine Besan',
  '500 g',
  'Grocery',
  66,
  'https://www.bbassets.com/media/uploads/p/s/30002289_7-tata-sampann-100-chana-dal-fine-besan.jpg'),
 ('Tata Sampann Chana Dal',
  '1 kg',
  'Grocery',
  124,
  'https://www.bbassets.com/media/uploads/p/s/40000290_12-tata-sampann-unpolished-chana-dal.jpg'),
 ('Tata Sampann Whole Masoor Dal',
  '1 kg',
  'Grocery',
  155,
  'https://www.bbassets.com/media/uploads/p/s/30002286_11-tata-sampann-unpolished-masoor-dal-whole.jpg'),
 ('Gaay Chhap Sabudana',
  '500 g',
  'Grocery',
  63,
  'https://www.bbassets.com/media/uploads/p/s/40048473_1-gaay-chhap-sabudana.jpg'),
 ('bb Royal Raw Peanuts',
  '500 g',
  'Grocery',
  115,
  'https://www.bbassets.com/media/uploads/p/s/10000442_22-bb-royal-peanuts-mungaphalishengdana-raw.jpg'),
 ('Organic Tattva Jaggery Powder',
  '500 g',
  'Grocery',
  76.95,
  'https://www.bbassets.com/media/uploads/p/s/40002647_5-organic-tattva-organic-powder-jaggery.jpg'),
 ('Amul Cow Ghee',
  '500 ml',
  'Dairy',
  348.25,
  'https://www.bbassets.com/media/uploads/p/s/40050542_6-amul-cow-ghee.jpg'),
 ('Amul Spiced Buttermilk',
  '200 ml',
  'Dairy',
  15,
  'https://www.bbassets.com/media/uploads/p/s/161899_10-amul-masti-buttermilk-spice.jpg'),
 ('Nescafe Classic Instant Coffee Powder',
  '45 g',
  'Beverages',
  230,
  'https://www.bbassets.com/media/uploads/p/s/267400_13-nescafe-classic-100-pure-instant-coffee.jpg')]


def upgrade() -> None:
    bind = op.get_bind()
    products = sa.table("products",
        sa.column("id", sa.Integer()), sa.column("name", sa.String()),
        sa.column("unit", sa.String()), sa.column("category", sa.String()),
        sa.column("price", sa.Float()), sa.column("image_url", sa.String()),
        sa.column("in_stock", sa.Boolean()), sa.column("stock_quantity", sa.Integer()))
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text(
            "SELECT setval(pg_get_serial_sequence('products', 'id'), "
            "COALESCE((SELECT MAX(id) FROM products), 1), "
            "(SELECT COUNT(*) > 0 FROM products))"))
    for name, unit, category, price, image_url in CATALOG_ROWS:
        existing = bind.execute(sa.select(products).where(
            sa.func.lower(products.c.name) == name.lower())).mappings().first()
        if existing:
            updates = {}
            if not existing["image_url"] and image_url:
                updates["image_url"] = image_url
            if existing["category"] == "Other":
                updates["category"] = category
            if updates:
                bind.execute(products.update().where(products.c.id == existing["id"]).values(**updates))
        else:
            bind.execute(products.insert().values(name=name, unit=unit,
                category=category, price=price, image_url=image_url,
                in_stock=True, stock_quantity=100))


def downgrade() -> None:
    # Keep business rows and photos; removing these could damage order history.
    pass
