"""Add delivery tracking fields and order messages table.

Revision ID: 0010
Revises: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("delivery_person_name", sa.String(length=100), nullable=True))
    op.add_column("orders", sa.Column("delivery_person_phone", sa.String(length=30), nullable=True))
    op.add_column("orders", sa.Column("delivery_token", sa.String(length=64), nullable=True))
    op.create_index("ix_orders_delivery_token", "orders", ["delivery_token"], unique=True)
    op.add_column("orders", sa.Column("delivery_lat", sa.Float(), nullable=True))
    op.add_column("orders", sa.Column("delivery_lng", sa.Float(), nullable=True))
    op.add_column("orders", sa.Column("delivery_location_updated_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "order_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), index=True, nullable=False),
        sa.Column("sender", sa.String(length=20), nullable=False),
        sa.Column("message", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("order_messages")
    op.drop_index("ix_orders_delivery_token", table_name="orders")
    op.drop_column("orders", "delivery_location_updated_at")
    op.drop_column("orders", "delivery_lng")
    op.drop_column("orders", "delivery_lat")
    op.drop_column("orders", "delivery_token")
    op.drop_column("orders", "delivery_person_phone")
    op.drop_column("orders", "delivery_person_name")
