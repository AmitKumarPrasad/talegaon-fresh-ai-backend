"""Bounded recovery of a lost customer refresh response."""
from alembic import op
import sqlalchemy as sa

revision = "0033_customer_refresh_retry"
down_revision = "0032_address_coordinates"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("customer_sessions", sa.Column("rotated_to_hash", sa.String(64), nullable=True))
    op.add_column("customer_sessions", sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("customer_sessions", "rotated_at")
    op.drop_column("customer_sessions", "rotated_to_hash")
