"""Customer REST API tables."""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("phone", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, server_default="Customer"),
        sa.Column("otp_hash", sa.String(64), nullable=True),
        sa.Column("otp_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cart", sa.JSON(), nullable=True),
    )
    op.create_table(
        "addresses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.String(50), sa.ForeignKey("customers.phone"), nullable=False),
        sa.Column("label", sa.String(50), nullable=False),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("pincode", sa.String(6), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_addresses_customer_id", "addresses", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_addresses_customer_id", table_name="addresses")
    op.drop_table("addresses")
    op.drop_table("customers")
