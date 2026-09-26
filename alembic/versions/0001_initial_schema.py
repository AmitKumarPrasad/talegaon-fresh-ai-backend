"""Initial Talegaon Fresh schema."""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("in_stock", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_products_name", "products", ["name"], unique=True)

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("total", sa.Float(), nullable=False, server_default="0"),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("payment_method", sa.String(20), nullable=True),
        sa.Column("payment_link_url", sa.String(500), nullable=True),
        sa.Column("razorpay_payment_link_id", sa.String(100), nullable=True),
        sa.Column("razorpay_payment_id", sa.String(100), nullable=True),
        sa.Column("razorpay_event_id", sa.String(100), nullable=True),
        sa.Column("payment_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])
    op.create_unique_constraint("uq_orders_razorpay_payment_link_id", "orders", ["razorpay_payment_link_id"])
    op.create_unique_constraint("uq_orders_razorpay_payment_id", "orders", ["razorpay_payment_id"])
    op.create_unique_constraint("uq_orders_razorpay_event_id", "orders", ["razorpay_event_id"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("product_name", sa.String(100), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("line_total", sa.Float(), nullable=False),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])

    op.create_table(
        "processed_webhooks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("event_id", sa.String(200), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "event_id", name="uq_processed_webhook_provider_event"),
    )

    op.create_table(
        "conversation_states",
        sa.Column("customer_id", sa.String(50), primary_key=True),
        sa.Column("step", sa.String(30), nullable=False, server_default="menu"),
        sa.Column("cart", sa.JSON(), nullable=True),
        sa.Column("pending_order_id", sa.Integer(), nullable=True),
        sa.Column("status_order_lookup", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_table("conversation_states")
    op.drop_table("processed_webhooks")
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")
    op.drop_constraint("uq_orders_razorpay_event_id", "orders", type_="unique")
    op.drop_constraint("uq_orders_razorpay_payment_id", "orders", type_="unique")
    op.drop_constraint("uq_orders_razorpay_payment_link_id", "orders", type_="unique")
    op.drop_index("ix_orders_customer_id", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_products_name", table_name="products")
    op.drop_table("products")
