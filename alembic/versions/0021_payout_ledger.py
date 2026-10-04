"""Create delivery partner payout and COD reconciliation ledger.

Revision ID: 0021_payout_ledger
Revises: 0020_delivery_otp
"""

from alembic import op
import sqlalchemy as sa

revision = "0021_payout_ledger"
down_revision = "0020_delivery_otp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delivery_payout_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("partner_phone", sa.String(length=30), nullable=False),
        sa.Column("payout_amount", sa.Float(), nullable=False),
        sa.Column("cod_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("order_id", name="uq_delivery_payout_order"),
    )
    op.create_index("ix_delivery_payout_ledger_order_id", "delivery_payout_ledger", ["order_id"], unique=False)
    op.create_index("ix_delivery_payout_ledger_partner_phone", "delivery_payout_ledger", ["partner_phone"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_delivery_payout_ledger_partner_phone", table_name="delivery_payout_ledger")
    op.drop_index("ix_delivery_payout_ledger_order_id", table_name="delivery_payout_ledger")
    op.drop_table("delivery_payout_ledger")
