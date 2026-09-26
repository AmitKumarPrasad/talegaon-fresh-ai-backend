"""Add product price history.

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_price_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_product_price_history_product_id", "product_price_history", ["product_id"])
    op.create_index("ix_product_price_history_effective_date", "product_price_history", ["effective_date"])


def downgrade() -> None:
    op.drop_index("ix_product_price_history_effective_date", table_name="product_price_history")
    op.drop_index("ix_product_price_history_product_id", table_name="product_price_history")
    op.drop_table("product_price_history")
