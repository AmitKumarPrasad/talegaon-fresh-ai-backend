"""Add verified catalog images and missing breakfast, dal, spice and snacks.

Price references were checked 2026-10-02. Existing selling prices and inventory
are retained. Freeze data here so future catalog changes cannot alter migrations.
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

CATALOG_ROWS = [('Amul Taaza Milk', '1 L', 'Dairy', 59, 'https://www.bbassets.com/media/uploads/p/s/40114416_9-amul-taaza-milk.jpg'), ('Amul Masti Dahi', '400 g', 'Dairy', 50, 'https://www.bbassets.com/media/uploads/p/s/104851_5-amul-masti-dahi.jpg'), ('Amul Fresh Malai Paneer', '200 g', 'Dairy', 76, 'https://www.bbassets.com/media/uploads/p/s/40096747_11-amul-malai-fresh-paneer.jpg'), ('Amul Butter', '100 g', 'Dairy', 63, 'https://www.bbassets.com/media/uploads/p/s/104860_10-amul-butter-pasteurised.jpg'), ('Amul Pure Milk Cheese Slices', '200 g', 'Dairy', 137, 'https://www.bbassets.com/media/uploads/p/s/104808_11-amul-cheese-slices.jpg'), ("Lay's Cream & Onion Chips", '58 g', 'Snacks', 17, 'https://www.bbassets.com/media/uploads/p/s/102745_20-lays-potato-chips-american-style-cream-onion-flavour.jpg'), ('Bingo Tedhe Medhe', '75 g', 'Snacks', 15, 'https://www.bbassets.com/media/uploads/p/s/40226709_12-bingo-tedhe-medhe-snacks-with-corn-rice-dal-masala-tadka.jpg'), ('Parle Hide & Seek', '100 g', 'Snacks', 26, 'https://www.bbassets.com/media/uploads/p/s/302121_15-parle-hide-seek-chocolate.jpg'), ('Britannia Jim Jam', '138 g', 'Snacks', 30.5, 'https://www.bbassets.com/media/uploads/p/s/270484_18-britannia-treat-jim-jam-cream-biscuits.jpg'), ("Chheda's Banana Chips", '170 g', 'Snacks', 67.5, 'https://www.bbassets.com/media/uploads/p/s/40137106_3-chhedas-chips-banana-salt-n-pepper.jpg'), ('Aashirvaad Whole Wheat Atta', '5 kg', 'Grocery', 266, 'https://www.bbassets.com/media/uploads/p/s/126903_12-aashirvaad-atta-whole-wheat.jpg'), ('India Gate Rozana Basmati Rice', '5 kg', 'Grocery', 470, 'https://www.bbassets.com/media/uploads/p/s/283426_7-india-gate-basmati-rice-feast-rozzana.jpg'), ('Tata Salt Iodised', '1 kg', 'Grocery', 28, 'https://www.bbassets.com/media/uploads/p/s/241600_11-tata-salt-iodized.jpg'), ('Sugar', '1 kg', 'Grocery', 55, None), ('Tata Sampann Toor Dal', '1 kg', 'Grocery', 199, 'https://www.bbassets.com/media/uploads/p/s/40000291_16-tata-sampann-unpolished-toor-dalarhar-dal.jpg'), ('Fortune Sunlite Sunflower Oil', '800 g', 'Grocery', 179, 'https://www.bbassets.com/media/uploads/p/s/274145_20-fortune-sun-lite-sunflower-refined-oil.jpg'), ('Maggi Masala Noodles', '280 g', 'Instant Food', 60, 'https://www.bbassets.com/media/uploads/p/s/266162_28-maggi-2-minute-instant-noodles-masala.jpg'), ('Tata Tea Gold', '500 g', 'Beverages', 200, 'https://www.bbassets.com/media/uploads/p/s/240067_24-tata-tea-gold-tea.jpg'), ('Harvest Gold Atta Bread', '450 g', 'Bakery & Breakfast', 59, 'https://www.bbassets.com/media/uploads/p/s/40026512_10-harvest-gold-bread-100-atta.jpg'), ('Catch Coriander Powder', '100 g', 'Masala & Spices', 32.8, 'https://www.bbassets.com/media/uploads/p/s/30006780_8-catch-coriander-powder.jpg'), ('Tata Sampann Thick Poha', '500 g', 'Bakery & Breakfast', 43.5, 'https://www.bbassets.com/media/uploads/p/s/40178083_11-tata-sampann-thick-poha.jpg'), ('Tata Sampann Moong Dal', '1 kg', 'Grocery', 155.5, 'https://www.bbassets.com/media/uploads/p/s/30002287_12-tata-sampann-unpolished-moong-dal.jpg'), ('Tata Sampann Turmeric Powder', '100 g', 'Masala & Spices', 37.44, 'https://www.bbassets.com/media/uploads/p/s/40070758_19-tata-sampann-turmeric-powder.jpg'), ("Haldiram's Aloo Bhujia", '200 g', 'Snacks', 60, 'https://www.bbassets.com/media/uploads/p/s/263128_5-haldirams-namkeen-aloo-bhujia.jpg')]


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
    # Remove only the fabricated URLs from the previous seed revision.
    legacy = sa.and_(products.c.image_url.like("https://images.bigbasket.com/p/%"),
                     products.c.image_url.like("%/260x260-c0bab6ba.jpg"))
    bind.execute(products.update().where(legacy).values(image_url=None))
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
