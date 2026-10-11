"""Persist checkout replay protection atomically with orders."""
from alembic import op
import sqlalchemy as sa
revision = "0030_checkout_requests"
down_revision = "0029_reviewer_orders"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("checkout_requests",
        sa.Column("customer_id", sa.String(50), primary_key=True),
        sa.Column("request_key", sa.String(100), primary_key=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False))

def downgrade():
    op.drop_table("checkout_requests")
