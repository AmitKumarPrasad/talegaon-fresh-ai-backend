"""Add the ready-to-cook cut vegetable pilot catalog."""

from alembic import op
import sqlalchemy as sa

revision = "0023_cut_vegetables"
down_revision = "0022_product_requests"
branch_labels = None
depends_on = None

CATALOG_ROWS = [
    ("Cut Potato", "500 g", "Ready-to-Cook", 45),
    ("Cut Onion", "500 g", "Ready-to-Cook", 45),
    ("Cut Carrot", "250 g", "Ready-to-Cook", 35),
    ("Cut Green Beans", "250 g", "Ready-to-Cook", 45),
    ("Cut Cabbage", "500 g", "Ready-to-Cook", 40),
    ("Cut Cauliflower", "500 g", "Ready-to-Cook", 50),
    ("Cut Mixed Vegetables", "500 g", "Ready-to-Cook", 70),
    ("Cut Bottle Gourd", "500 g", "Ready-to-Cook", 40),
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
    for name, unit, category, price in CATALOG_ROWS:
        existing = bind.execute(
            sa.select(products).where(sa.func.lower(products.c.name) == name.lower())
        ).mappings().first()
        if existing:
            updates = {}
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
                image_url=None,
                in_stock=True,
                stock_quantity=100,
            ))


def downgrade() -> None:
    # Keep catalog rows because they may already be referenced by orders.
    pass
