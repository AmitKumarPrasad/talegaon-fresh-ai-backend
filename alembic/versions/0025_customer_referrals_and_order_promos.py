"""Add customer referral codes and authoritative checkout adjustments."""

from alembic import op
import sqlalchemy as sa

revision = "0025_customer_referrals_and_order_promos"
down_revision = "0024_partner_batches_earnings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column("referral_code", sa.String(length=24), nullable=True),
    )
    op.create_index(
        "ix_customers_referral_code",
        "customers",
        ["referral_code"],
        unique=True,
    )
    op.add_column(
        "orders",
        sa.Column("delivery_fee", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "orders",
        sa.Column("discount_amount", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "orders",
        sa.Column("promo_code", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "promo_code")
    op.drop_column("orders", "discount_amount")
    op.drop_column("orders", "delivery_fee")
    op.drop_index("ix_customers_referral_code", table_name="customers")
    op.drop_column("customers", "referral_code")
