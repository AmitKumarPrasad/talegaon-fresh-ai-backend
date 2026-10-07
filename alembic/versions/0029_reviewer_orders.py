"""Isolate reviewer orders from production fulfillment."""
from alembic import op
import sqlalchemy as sa
revision = "0029_reviewer_orders"
down_revision = "0028_expand_alembic_version_column"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("reviewer_orders", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("customer_id", sa.String(50), nullable=False),
                    sa.Column("snapshot", sa.JSON(), nullable=False))
    op.create_index("ix_reviewer_orders_customer_id", "reviewer_orders", ["customer_id"])

def downgrade():
    op.drop_table("reviewer_orders")
