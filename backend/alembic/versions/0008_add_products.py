"""product library: add organization-scoped products

Revision ID: 0008_add_products
Revises: 0007_expand_org_roles
Create Date: 2026-08-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0008_add_products"
down_revision: Union[str, None] = "0007_expand_org_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("barcode", sa.String(length=255), nullable=True),
        sa.Column("composition", sa.Text(), nullable=False),
        sa.Column(
            "emissions_value", sa.Numeric(precision=18, scale=6), nullable=False
        ),
        sa.Column("emissions_unit", sa.String(length=100), nullable=False),
        sa.Column("emissions_description", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "emissions_value >= 0", name="ck_products_emissions_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "barcode",
            name="uq_products_organization_barcode",
        ),
    )
    op.create_index("ix_products_organization_id", "products", ["organization_id"])
    op.create_index("ix_products_name", "products", ["name"])


def downgrade() -> None:
    op.drop_index("ix_products_name", table_name="products")
    op.drop_index("ix_products_organization_id", table_name="products")
    op.drop_table("products")
