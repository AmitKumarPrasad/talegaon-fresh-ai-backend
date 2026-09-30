"""Add secure customer PIN credentials and refresh sessions."""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "customer_pin_credentials",
        sa.Column("customer_id", sa.String(length=50), sa.ForeignKey("customers.phone"), primary_key=True),
        sa.Column("pin_hash", sa.String(length=200), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "customer_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.String(length=50), sa.ForeignKey("customers.phone"), nullable=False),
        sa.Column("device_id", sa.String(length=200), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_customer_sessions_customer_id", "customer_sessions", ["customer_id"])
    op.create_index("ix_customer_sessions_refresh_token_hash", "customer_sessions", ["refresh_token_hash"], unique=True)

def downgrade() -> None:
    op.drop_index("ix_customer_sessions_refresh_token_hash", table_name="customer_sessions")
    op.drop_index("ix_customer_sessions_customer_id", table_name="customer_sessions")
    op.drop_table("customer_sessions")
    op.drop_table("customer_pin_credentials")
