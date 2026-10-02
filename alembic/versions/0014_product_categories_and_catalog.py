"""Add product categories and expand the baseline grocery catalog."""

from alembic import op
import sqlalchemy as sa


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


BASELINE_PRODUCTS = [
    ("Tomato", "1 kg", "Vegetables", 40),
    ("Potato", "1 kg", "Vegetables", 35),
    ("Onion", "1 kg", "Vegetables", 40),
    ("Carrot", "500 g", "Vegetables", 50),
    ("Capsicum", "500 g", "Vegetables", 70),
    ("Cabbage", "1 pc", "Vegetables", 30),
    ("Cauliflower", "1 pc", "Vegetables", 40),
    ("Ladyfinger", "500 g", "Vegetables", 60),
    ("Green Beans", "500 g", "Vegetables", 80),
    ("Spinach", "1 bunch", "Leafy Greens", 30),
    ("Coriander", "1 bunch", "Leafy Greens", 20),
    ("Green Chilli", "250 g", "Vegetables", 30),
    ("Ginger", "250 g", "Vegetables", 40),
    ("Garlic", "250 g", "Vegetables", 50),
    ("Banana", "1 dozen", "Fruits", 60),
    ("Apple", "1 kg", "Fruits", 160),
    ("Orange", "1 kg", "Fruits", 90),
    ("Grapes", "500 g", "Fruits", 100),
    ("Pomegranate", "1 kg", "Fruits", 140),
    ("Papaya", "1 pc", "Fruits", 60),
    ("Amul Taaza Milk", "1 L", "Dairy", 59),
    ("Amul Masti Dahi", "400 g", "Dairy", 50),
    ("Amul Fresh Malai Paneer", "200 g", "Dairy", 95),
    ("Amul Butter", "100 g", "Dairy", 63),
    ("Amul Pure Milk Cheese Slices", "200 g", "Dairy", 137),
    ("Lay's Cream & Onion Chips", "58 g", "Snacks", 20),
    ("Bingo Tedhe Medhe", "75 g", "Snacks", 14),
    ("Parle Hide & Seek", "100 g", "Snacks", 26),
    ("Britannia Jim Jam", "138 g", "Snacks", 35),
    ("Chheda's Banana Chips", "170 g", "Snacks", 70),
    ("Aashirvaad Whole Wheat Atta", "5 kg", "Grocery", 264),
    ("India Gate Rozana Basmati Rice", "5 kg", "Grocery", 454),
    ("Tata Salt Iodised", "1 kg", "Grocery", 29),
    ("Sugar", "1 kg", "Grocery", 69),
    ("Tata Sampann Toor Dal", "1 kg", "Grocery", 174),
    ("Fortune Sunlite Sunflower Oil", "840 g", "Grocery", 177),
    ("Maggi Masala Noodles", "280 g", "Instant Food", 60),
    ("Tata Tea Gold", "500 g", "Beverages", 264),
    ("Harvest Gold Atta Bread", "450 g", "Bakery & Breakfast", 65),
    ("Catch Coriander Powder", "100 g", "Masala & Spices", 32),
]


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "category",
            sa.String(50),
            nullable=False,
            server_default="Other",
        ),
    )

    bind = op.get_bind()
    products = sa.table(
        "products",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("unit", sa.String()),
        sa.column("category", sa.String()),
        sa.column("price", sa.Float()),
        sa.column("in_stock", sa.Boolean()),
        sa.column("stock_quantity", sa.Integer()),
        sa.column("image_url", sa.String()),
    )

    # Older seed code inserted explicit IDs. Keep PostgreSQL's sequence ahead of
    # existing rows before adding new records without hard-coded IDs.
    if bind.dialect.name == "postgresql":
        bind.execute(
            sa.text(
                "SELECT setval("
                "pg_get_serial_sequence('products', 'id'), "
                "COALESCE((SELECT MAX(id) FROM products), 1), "
                "(SELECT COUNT(*) > 0 FROM products)"
                ")"
            )
        )

    existing_names = {
        value.lower()
        for value in bind.execute(sa.select(products.c.name)).scalars()
        if value
    }

    for name, unit, category, price in BASELINE_PRODUCTS:
        if name.lower() in existing_names:
            bind.execute(
                products.update()
                .where(sa.func.lower(products.c.name) == name.lower())
                .values(category=category)
            )
            continue

        bind.execute(
            products.insert().values(
                name=name,
                unit=unit,
                category=category,
                price=float(price),
                in_stock=True,
                stock_quantity=100,
                image_url=None,
            )
        )
        existing_names.add(name.lower())


def downgrade() -> None:
    # Product rows are retained to avoid deleting business data during rollback.
    op.drop_column("products", "category")
