"""Add household and personal care catalog products with verified references."""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

CATALOG_ROWS = [
    ("Surf Excel Matic Front Load Detergent Powder", "1 kg", "Household", 290, "https://www.bbassets.com/media/uploads/p/s/100142980_22-surf-excel-matic-front-load-detergent-powder.jpg"),
    ("Vim Lemon Dishwash Liquid Gel", "500 ml", "Household", 125, "https://www.bbassets.com/media/uploads/p/s/266962_13-vim-dishwash-liquid-gel-lemon.jpg"),
    ("Harpic Floral Bathroom Cleaner", "500 ml", "Household", 120, "https://www.bbassets.com/media/uploads/p/s/40017766_15-harpic-disinfectant-bathroom-cleaner-liquid-floral.jpg"),
    ("Colgate Strong Teeth Toothpaste", "100 g", "Personal Care", 73, "https://www.bbassets.com/media/uploads/p/s/100006161_31-colgate-strong-teeth-anticavity-toothpaste-with-amino-shakti-formula-provides-fresher-breath.jpg"),
    ("Dettol Skincare Liquid Handwash", "250 ml", "Personal Care", 99, "https://www.bbassets.com/media/uploads/p/s/40196286_1-dettol-skincare-germ-protection-liquid-handwash.jpg"),
    ("Lux Soft Glow Rose Soap", "100 g", "Personal Care", 36, "https://www.bbassets.com/media/uploads/p/s/306171_8-lux-beauty-soap-for-glowing-skin-rose-vitamin-e.jpg"),
    ("Ariel Matic Top Load Detergent Powder", "1 kg", "Household", 309, "https://www.bbassets.com/media/uploads/p/s/40097082_16-ariel-matic-detergent-washing-powder-top-load.jpg"),
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
