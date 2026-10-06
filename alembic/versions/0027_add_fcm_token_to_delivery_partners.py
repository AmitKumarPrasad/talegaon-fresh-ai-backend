"""Add FCM token column to delivery_partners table for push notifications."""

from alembic import op
import sqlalchemy as sa

revision = "0027_add_fcm_token_to_delivery_partners"
down_revision = "0026_add_fcm_token_to_customers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "delivery_partners",
        sa.Column("fcm_token", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("delivery_partners", "fcm_token")
