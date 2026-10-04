"""delivery OTP verification fields

Revision ID: 0020_delivery_otp
Revises: 0019_delivery_partner
"""

from alembic import op
import sqlalchemy as sa

revision = "0020_delivery_otp"
down_revision = "0019_delivery_partner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("delivery_otp_hash", sa.String(length=64), nullable=True))
    op.add_column("orders", sa.Column("delivery_otp_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("delivery_otp_attempts", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("orders", "delivery_otp_attempts")
    op.drop_column("orders", "delivery_otp_expires_at")
    op.drop_column("orders", "delivery_otp_hash")
