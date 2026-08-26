"""create initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- organizations ---
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("industry_type", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                   server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                   server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organizations_name", "organizations", ["name"])
    op.create_index("ix_organizations_industry_type", "organizations", ["industry_type"])

    # --- facilities ---
    op.create_table(
        "facilities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=False),
        sa.Column("facility_type", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                   server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                   server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_facilities_organization_id", "facilities", ["organization_id"])
    op.create_index("ix_facilities_name", "facilities", ["name"])
    op.create_index("ix_facilities_facility_type", "facilities", ["facility_type"])

    # --- source_type_enum (PostgreSQL native enum) ---
    source_type_enum = sa.Enum("ENERGY", "FUEL", "RESOURCE", name="source_type_enum")
    source_type_enum.create(op.get_bind(), checkfirst=True)

    # --- emission_sources ---
    op.create_table(
        "emission_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("facility_id", sa.Integer(), nullable=False),
        sa.Column(
            "source_type",
            postgresql.ENUM("ENERGY", "FUEL", "RESOURCE", name="source_type_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("unit_of_measurement", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                   server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                   server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_emission_sources_facility_id", "emission_sources", ["facility_id"])
    op.create_index("ix_emission_sources_source_type", "emission_sources", ["source_type"])
    op.create_index("ix_emission_sources_source_name", "emission_sources", ["source_name"])

    # --- emission_factors (expanded) ---
    op.create_table(
        "emission_factors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("region", sa.String(length=100), nullable=False),
        sa.Column("factor_value", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                   server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                   server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_emission_factors_source_type", "emission_factors", ["source_type"])
    op.create_index("ix_emission_factors_region", "emission_factors", ["region"])
    op.create_index("ix_emission_factors_source_type_region", "emission_factors",
                     ["source_type", "region"])

    # --- consumption_records ---
    op.create_table(
        "consumption_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("emission_source_id", sa.Integer(), nullable=False),
        sa.Column("facility_id", sa.Integer(), nullable=False),
        sa.Column("quantity_consumed", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                   server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                   server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["emission_source_id"], ["emission_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["facility_id"], ["facilities.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_consumption_records_emission_source_id", "consumption_records", ["emission_source_id"])
    op.create_index("ix_consumption_records_facility_id", "consumption_records", ["facility_id"])

    # --- emission_calculations ---
    op.create_table(
        "emission_calculations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("consumption_record_id", sa.Integer(), nullable=False),
        sa.Column("emission_factor_id", sa.Integer(), nullable=False),
        sa.Column("calculated_emissions_kg_co2e", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column("calculation_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                   server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["consumption_record_id"], ["consumption_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["emission_factor_id"], ["emission_factors.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_emission_calculations_consumption_record_id", "emission_calculations", ["consumption_record_id"])
    op.create_index("ix_emission_calculations_emission_factor_id", "emission_calculations", ["emission_factor_id"])

    # --- report_status_enum (PostgreSQL native enum) ---
    report_status_enum = sa.Enum("DRAFT", "FINAL", name="report_status_enum")
    report_status_enum.create(op.get_bind(), checkfirst=True)

    # --- reports ---
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("report_period_start", sa.Date(), nullable=False),
        sa.Column("report_period_end", sa.Date(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False,
                   server_default=sa.func.now()),
        sa.Column(
            "status",
            postgresql.ENUM("DRAFT", "FINAL", name="report_status_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                   server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                   server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_reports_organization_id", "reports", ["organization_id"])


def downgrade() -> None:
    # Drop tables in reverse FK-dependency order
    op.drop_table("reports")
    op.drop_table("emission_calculations")
    op.drop_table("consumption_records")
    op.drop_table("emission_factors")
    op.drop_table("emission_sources")
    op.drop_table("facilities")
    op.drop_table("organizations")

    # Drop the PostgreSQL enum types
    sa.Enum(name="report_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="source_type_enum").drop(op.get_bind(), checkfirst=True)
