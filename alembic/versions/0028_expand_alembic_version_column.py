"""Expand alembic_version.version_num column to support longer migration names.

Revision ID: 0028_expand_alembic_version_column
Revises: 0027_add_fcm_token_to_delivery_partners
Create Date: 2026-10-06 09:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0028_expand_alembic_version_column'
down_revision = '0027_add_fcm_token_to_delivery_partners'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Expand version_num column from VARCHAR(32) to VARCHAR(255)
    # to support longer migration identifiers like '0025_customer_referrals_and_order_promos'
    op.alter_column(
        'alembic_version',
        'version_num',
        existing_type=sa.VARCHAR(length=32),
        type_=sa.VARCHAR(length=255),
        existing_nullable=False
    )


def downgrade() -> None:
    # Revert to original column size if needed
    op.alter_column(
        'alembic_version',
        'version_num',
        existing_type=sa.VARCHAR(length=255),
        type_=sa.VARCHAR(length=32),
        existing_nullable=False
    )
