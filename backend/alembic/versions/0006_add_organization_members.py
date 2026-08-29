"""authorization: organization_members, plus source/facility tenant integrity

Revision ID: 0006_org_members
Revises: 0005_add_audit_logs
Create Date: 2026-08-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006_org_members"
down_revision: Union[str, None] = "0005_add_audit_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # The membership table every access check now resolves against.
    # ------------------------------------------------------------------
    op.create_table(
        "organization_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        # No server_default on purpose: the role is assigned explicitly in
        # application code, so a path that forgets it fails on NOT NULL
        # rather than inheriting an implied role.
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "organization_id", name="uq_organization_members_user_org"
        ),
        # Makes an invalid role unrepresentable at the storage layer, not
        # merely unwritten by the current handlers.
        sa.CheckConstraint("role IN ('OWNER')", name="ck_organization_members_role"),
    )
    op.create_index(
        "ix_organization_members_user_id", "organization_members", ["user_id"]
    )
    op.create_index(
        "ix_organization_members_organization_id",
        "organization_members",
        ["organization_id"],
    )

    # ------------------------------------------------------------------
    # Tenant integrity for consumption records.
    #
    # A record names both an emission source and a facility. Nothing until
    # now required those to agree, so a record could attribute one
    # facility's consumption to another facility's — potentially another
    # organization's — source. The composite foreign key makes that
    # unrepresentable, which an application check alone cannot guarantee for
    # every future write path.
    #
    # A composite FK needs a unique constraint to target, hence the
    # (id, facility_id) uniqueness on emission_sources: redundant in itself,
    # since id is already the primary key, but required as the reference.
    # ------------------------------------------------------------------
    op.create_unique_constraint(
        "uq_emission_sources_id_facility_id",
        "emission_sources",
        ["id", "facility_id"],
    )
    op.create_foreign_key(
        "fk_consumption_records_source_facility",
        "consumption_records",
        "emission_sources",
        ["emission_source_id", "facility_id"],
        ["id", "facility_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_consumption_records_source_facility",
        "consumption_records",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_emission_sources_id_facility_id", "emission_sources", type_="unique"
    )
    op.drop_index(
        "ix_organization_members_organization_id", table_name="organization_members"
    )
    op.drop_index("ix_organization_members_user_id", table_name="organization_members")
    op.drop_table("organization_members")
