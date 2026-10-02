"""Add eggs and dry-fruit catalog products with verified references."""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

CATALOG_ROWS = [
    ("SKM Best Fresh Eggs", "6 pcs", "Eggs", 84, "https://www.bbassets.com/media/uploads/p/s/40348991_1-skm-best-fresh-eggs.jpg"),
    ("Tata Sampann California Almonds", "200 g", "Dry Fruits", 251.16, "https://www.bbassets.com/media/uploads/p/s/40309615_7-tata-sampann-100-pure-california-almonds-whole-premium-quality-badam-giri.jpg"),
    ("Happilo Premium Whole Cashews", "200 g", "Dry Fruits", 282, "https://www.bbassets.com/media/uploads/p/s/40087196_7-happilo-premium-natural-whole-cashews.jpg"),
    ("bb Popular Indian Raisins", "200 g", "Dry Fruits", 100, "https://www.bbassets.com/media/uploads/p/s/40002629_11-bb-popular-raisinskishmish-indian.jpg"),
    ("Happilo Premium International Queen Kalmi Dates", "200 g", "Dry Fruits", 330.45, "https://www.bbassets.com/media/uploads/p/s/40123722_7-happilo-premium-international-queen-kalmi-dates.jpg"),
]

def upgrade() -> None:
    bind = op.get_bind()
    products = sa.table(
        "products",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("unit", sa.String()),
        sa.column("category", sa.String()),
        sa.column("price", sa.Float()),
        sa.column("image_url", sa.String()),
        sa.column("in_stock", sa.Boolean()),
        sa.column("stock_quantity", sa.Integer()),
    )
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text(
            "SELECT setval(pg_get_serial_sequence('products', 'id'), "
            "COALESCE((SELECT MAX(id) FROM products), 1), "
            "(SELECT COUNT(*) > 0 FROM products))"
        ))
    for name, unit, category, price, image_url in CATALOG_ROWS:
        existing = bind.execute(
            sa.select(products).where(sa.func.lower(products.c.name) == name.lower())
        ).mappings().first()
        if existing:
            updates = {}
            if not existing["image_url"]:
                updates["image_url"] = image_url
            if existing["category"] == "Other":
                updates["category"] = category
            if updates:
                bind.execute(
                    products.update().where(products.c.id == existing["id"]).values(**updates)
                )
        else:
            bind.execute(products.insert().values(
                name=name,
                unit=unit,
                category=category,
                price=price,
                image_url=image_url,
                in_stock=True,
                stock_quantity=100,
            ))

def downgrade() -> None:
    # Keep catalog rows because they may already be referenced by orders.
    pass
