"""add organization join codes and membership lifecycle

Revision ID: 0009_membership_lifecycle
Revises: 0008_add_products
Create Date: 2026-08-31
"""

import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_membership_lifecycle"
down_revision: Union[str, None] = "0008_add_products"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JOIN_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _join_code() -> str:
    groups = [
        "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(4))
        for _ in range(6)
    ]
    return "ORG-" + "-".join(groups)


def upgrade() -> None:
    # Add nullable first so existing organizations can be assigned unique
    # values before NOT NULL and uniqueness are enforced.
    op.add_column(
        "organizations", sa.Column("join_code", sa.String(length=40), nullable=True)
    )
    connection = op.get_bind()
    organization_ids = connection.execute(
        sa.text("SELECT id FROM organizations ORDER BY id")
    ).scalars()
    generated: set[str] = set()
    for organization_id in organization_ids:
        code = _join_code()
        while code in generated:
            code = _join_code()
        generated.add(code)
        connection.execute(
            sa.text("UPDATE organizations SET join_code = :code WHERE id = :id"),
            {"code": code, "id": organization_id},
        )
    op.alter_column("organizations", "join_code", nullable=False)
    op.create_index(
        "ix_organizations_join_code", "organizations", ["join_code"], unique=True
    )

    op.create_table(
        "organization_join_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_organization_join_requests_status",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND decided_at IS NULL) OR "
            "(status IN ('APPROVED', 'REJECTED') AND decided_at IS NOT NULL)",
            name="ck_organization_join_requests_decision_time",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_organization_join_requests_pending_user_org",
        "organization_join_requests",
        ["user_id", "organization_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "ix_organization_join_requests_org_status",
        "organization_join_requests",
        ["organization_id", "status"],
    )
    op.create_index(
        "ix_organization_join_requests_user_status",
        "organization_join_requests",
        ["user_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_organization_join_requests_user_status",
        table_name="organization_join_requests",
    )
    op.drop_index(
        "ix_organization_join_requests_org_status",
        table_name="organization_join_requests",
    )
    op.drop_index(
        "uq_organization_join_requests_pending_user_org",
        table_name="organization_join_requests",
    )
    op.drop_table("organization_join_requests")
    op.drop_index("ix_organizations_join_code", table_name="organizations")
    op.drop_column("organizations", "join_code")

