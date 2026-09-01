"""persist generated product barcode PNGs

Revision ID: 0010_product_barcode_images
Revises: 0009_membership_lifecycle
Create Date: 2026-09-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_product_barcode_images"
down_revision: Union[str, None] = "0009_membership_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("barcode_image", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "barcode_image")
