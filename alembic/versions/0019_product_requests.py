"""Create customer product request inbox."""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.String(length=50), sa.ForeignKey("customers.phone"), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("request_text", sa.String(length=1000), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="NEW"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_product_requests_customer_id", "product_requests", ["customer_id"])
    op.create_index("ix_product_requests_order_id", "product_requests", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_product_requests_order_id", table_name="product_requests")
    op.drop_index("ix_product_requests_customer_id", table_name="product_requests")
    op.drop_table("product_requests")
