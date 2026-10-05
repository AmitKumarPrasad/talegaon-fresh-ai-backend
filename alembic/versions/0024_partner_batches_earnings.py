"""Add delivery batches and transparent partner payout components."""

from alembic import op
import sqlalchemy as sa

revision = "0024_partner_batches_earnings"
down_revision = "0023_cut_vegetables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("delivery_batch_id", sa.String(length=64), nullable=True))
    op.add_column("orders", sa.Column("delivery_sequence", sa.Integer(), nullable=True))
    op.add_column("orders", sa.Column("delivery_distance_km", sa.Float(), server_default="0", nullable=False))
    op.add_column("orders", sa.Column("delivery_incentive", sa.Float(), server_default="0", nullable=False))
    op.create_index("ix_orders_delivery_batch_id", "orders", ["delivery_batch_id"])

    op.add_column("delivery_payout_ledger", sa.Column("base_amount", sa.Float(), server_default="25", nullable=False))
    op.add_column("delivery_payout_ledger", sa.Column("distance_km", sa.Float(), server_default="0", nullable=False))
    op.add_column("delivery_payout_ledger", sa.Column("distance_amount", sa.Float(), server_default="0", nullable=False))
    op.add_column("delivery_payout_ledger", sa.Column("incentive_amount", sa.Float(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("delivery_payout_ledger", "incentive_amount")
    op.drop_column("delivery_payout_ledger", "distance_amount")
    op.drop_column("delivery_payout_ledger", "distance_km")
    op.drop_column("delivery_payout_ledger", "base_amount")
    op.drop_index("ix_orders_delivery_batch_id", table_name="orders")
    op.drop_column("orders", "delivery_incentive")
    op.drop_column("orders", "delivery_distance_km")
    op.drop_column("orders", "delivery_sequence")
    op.drop_column("orders", "delivery_batch_id")
