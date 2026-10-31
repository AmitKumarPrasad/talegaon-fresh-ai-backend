from alembic import op
import sqlalchemy as sa

revision = "0032_address_coordinates"
down_revision = "0031_campaigns"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("addresses", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("addresses", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("orders", sa.Column("destination_latitude", sa.Float(), nullable=True))
    op.add_column("orders", sa.Column("destination_longitude", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("orders", "destination_longitude")
    op.drop_column("orders", "destination_latitude")
    op.drop_column("addresses", "longitude")
    op.drop_column("addresses", "latitude")
