"""Add expiry timestamps to delivery bearer links."""
from datetime import datetime, timedelta, timezone

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("delivery_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    orders = sa.table(
        "orders",
        sa.column("delivery_token", sa.String(length=64)),
        sa.column("delivery_token_expires_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        orders.update()
        .where(orders.c.delivery_token.isnot(None))
        .values(delivery_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=24))
    )


def downgrade() -> None:
    op.drop_column("orders", "delivery_token_expires_at")
