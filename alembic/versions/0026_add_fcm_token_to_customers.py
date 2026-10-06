"""Add FCM token column to customers table for push notifications."""

from alembic import op
import sqlalchemy as sa

revision = "0026_add_fcm_token_to_customers"
down_revision = "0025_customer_referrals_and_order_promos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column("fcm_token", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("customers", "fcm_token")
