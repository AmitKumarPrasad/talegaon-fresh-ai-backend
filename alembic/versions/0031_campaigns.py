"""Add admin-controlled banners and promotions."""
from alembic import op
import sqlalchemy as sa

revision = "0031_campaigns"
down_revision = "0030_checkout_requests"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "promotions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("discount_type", sa.String(10), nullable=False),
        sa.Column("discount_value", sa.Float(), nullable=False),
        sa.Column("min_order", sa.Float(), nullable=False),
        sa.Column("max_discount", sa.Float(), nullable=True),
        sa.Column("first_order_only", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "campaign_banners",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("promo_code", sa.String(32), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("campaign_banners")
    op.drop_table("promotions")
