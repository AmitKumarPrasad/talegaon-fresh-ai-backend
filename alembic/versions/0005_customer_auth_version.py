"""Add customer auth version for token revocation."""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("auth_version", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("customers", "auth_version")
