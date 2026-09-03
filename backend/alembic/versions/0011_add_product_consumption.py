"""Product consumption configuration and immutable consumption snapshots.

Revision ID: 0011_product_consumption
Revises: 0010_product_barcode_images
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_product_consumption"
down_revision = "0010_product_barcode_images"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("consumption_unit", sa.String(50), nullable=True))
    op.add_column("products", sa.Column("consumption_source_type", sa.String(8), nullable=True))
    op.create_check_constraint(
        "ck_products_consumption_configuration", "products",
        "(consumption_unit IS NULL AND consumption_source_type IS NULL) OR "
        "(consumption_unit IS NOT NULL AND consumption_source_type IS NOT NULL "
        "AND consumption_source_type IN ('ENERGY', 'FUEL', 'RESOURCE') "
        "AND length(trim(consumption_unit)) > 0 "
        "AND consumption_unit = trim(consumption_unit) "
        "AND emissions_unit = 'kg CO2e/' || consumption_unit)",
    )
    op.create_unique_constraint("uq_products_id_organization_id", "products", ["id", "organization_id"])
    op.create_unique_constraint("uq_facilities_id_organization_id", "facilities", ["id", "organization_id"])
    op.alter_column("consumption_records", "emission_source_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("emission_calculations", "emission_factor_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("consumption_records", sa.Column("product_id", sa.Integer(), nullable=True))
    op.add_column("consumption_records", sa.Column("product_organization_id", sa.Integer(), nullable=True))
    # none_as_null also makes explicit None values SQL NULL instead of JSON null.
    op.add_column("consumption_records", sa.Column("product_snapshot", sa.JSON(none_as_null=True), nullable=True))
    op.add_column("consumption_records", sa.Column("product_source_type", sa.String(8), nullable=True))
    op.create_foreign_key(
        "fk_consumption_records_product_organization", "consumption_records", "products",
        ["product_id", "product_organization_id"], ["id", "organization_id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_consumption_records_product_facility_organization", "consumption_records", "facilities",
        ["facility_id", "product_organization_id"], ["id", "organization_id"], ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_consumption_records_source_or_product", "consumption_records",
        "(emission_source_id IS NOT NULL AND product_id IS NULL "
        "AND product_organization_id IS NULL AND product_snapshot IS NULL "
        "AND product_source_type IS NULL) OR "
        "(emission_source_id IS NULL AND product_snapshot IS NOT NULL "
        "AND product_source_type IS NOT NULL "
        "AND product_source_type IN ('ENERGY', 'FUEL', 'RESOURCE') "
        "AND ((product_id IS NULL AND product_organization_id IS NULL) OR "
        "(product_id IS NOT NULL AND product_organization_id IS NOT NULL)))",
    )
    op.create_index("ix_consumption_records_product_id", "consumption_records", ["product_id"])


def downgrade() -> None:
    # Refuse to erase Product history or force null source/factor IDs into
    # NOT NULL columns. A data-retention decision is required first.
    connection = op.get_bind()
    if connection.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM consumption_records WHERE product_snapshot IS NOT NULL)"
    )).scalar():
        raise RuntimeError("Cannot downgrade while Product consumption records exist")
    op.drop_index("ix_consumption_records_product_id", table_name="consumption_records")
    op.drop_constraint("ck_consumption_records_source_or_product", "consumption_records", type_="check")
    op.drop_constraint("fk_consumption_records_product_facility_organization", "consumption_records", type_="foreignkey")
    op.drop_constraint("fk_consumption_records_product_organization", "consumption_records", type_="foreignkey")
    for column in ("product_source_type", "product_snapshot", "product_organization_id", "product_id"):
        op.drop_column("consumption_records", column)
    op.alter_column("emission_calculations", "emission_factor_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("consumption_records", "emission_source_id", existing_type=sa.Integer(), nullable=False)
    op.drop_constraint("uq_facilities_id_organization_id", "facilities", type_="unique")
    op.drop_constraint("uq_products_id_organization_id", "products", type_="unique")
    op.drop_constraint("ck_products_consumption_configuration", "products", type_="check")
    op.drop_column("products", "consumption_source_type")
    op.drop_column("products", "consumption_unit")
