"""Add Google identity mapping for customer sign-in."""
from alembic import op
import sqlalchemy as sa

revision = "0031_google_customer_identity"
down_revision = "0030_checkout_requests"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customer_google_identities",
        sa.Column("provider_subject", sa.String(255), primary_key=True),
        sa.Column(
            "customer_id",
            sa.String(50),
            sa.ForeignKey("customers.phone", ondelete="CASCADE"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("customer_google_identities")
