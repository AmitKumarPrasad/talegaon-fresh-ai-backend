"""Add product stock quantities for transactional order reservation."""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("stock_quantity", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute("UPDATE products SET stock_quantity = 100 WHERE in_stock = TRUE")


def downgrade() -> None:
    op.drop_column("products", "stock_quantity")
