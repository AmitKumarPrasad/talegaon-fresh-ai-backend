"""delivery partner accounts and delivery lifecycle

Revision ID: 0019_delivery_partner
Revises: 0018_eggs_and_dry_fruits
"""

from alembic import op
import sqlalchemy as sa

revision = "0019_delivery_partner"
down_revision = "0018_eggs_and_dry_fruits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("delivery_status", sa.String(length=30), nullable=True))
    op.create_index("ix_orders_delivery_status", "orders", ["delivery_status"])
    op.create_table(
        "delivery_partners",
        sa.Column("phone", sa.String(length=30), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("pin_hash", sa.String(length=200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "delivery_partner_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("partner_phone", sa.String(length=30), sa.ForeignKey("delivery_partners.phone"), nullable=False),
        sa.Column("device_id", sa.String(length=200), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_delivery_partner_sessions_partner_phone", "delivery_partner_sessions", ["partner_phone"])
    op.create_index("ix_delivery_partner_sessions_refresh_token_hash", "delivery_partner_sessions", ["refresh_token_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_delivery_partner_sessions_refresh_token_hash", table_name="delivery_partner_sessions")
    op.drop_index("ix_delivery_partner_sessions_partner_phone", table_name="delivery_partner_sessions")
    op.drop_table("delivery_partner_sessions")
    op.drop_table("delivery_partners")
    op.drop_index("ix_orders_delivery_status", table_name="orders")
    op.drop_column("orders", "delivery_status")
