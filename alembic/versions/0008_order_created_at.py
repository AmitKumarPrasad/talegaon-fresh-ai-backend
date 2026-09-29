"""Add order creation timestamp.

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(sa.text("UPDATE orders SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
    op.alter_column("orders", "created_at", nullable=False)


def downgrade() -> None:
    op.drop_column("orders", "created_at")
