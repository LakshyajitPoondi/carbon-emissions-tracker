"""add barcode_value to emission_sources

Revision ID: 0003_add_barcode
Revises: 0002_add_users
Create Date: 2026-08-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_add_barcode"
down_revision: Union[str, None] = "0002_add_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "emission_sources",
        sa.Column("barcode_value", sa.String(length=255), nullable=True),
    )
    # Postgres unique indexes treat each NULL as distinct, so sources without
    # a barcode yet don't collide with each other — no partial WHERE clause
    # needed.
    op.create_index(
        "ix_emission_sources_facility_id_barcode_value",
        "emission_sources",
        ["facility_id", "barcode_value"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_emission_sources_facility_id_barcode_value", table_name="emission_sources")
    op.drop_column("emission_sources", "barcode_value")
