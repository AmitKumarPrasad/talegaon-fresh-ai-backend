"""Harden customer OTP security."""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("otp_window_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("customers", sa.Column("otp_request_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("customers", sa.Column("otp_failed_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("customers", sa.Column("otp_locked_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("customers", "otp_locked_until")
    op.drop_column("customers", "otp_failed_attempts")
    op.drop_column("customers", "otp_request_count")
    op.drop_column("customers", "otp_window_started_at")
