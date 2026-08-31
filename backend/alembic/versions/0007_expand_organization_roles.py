"""authorization: add ADMIN and EMPLOYEE organization roles

Revision ID: 0007_expand_org_roles
Revises: 0006_org_members
Create Date: 2026-08-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0007_expand_org_roles"
down_revision: Union[str, None] = "0006_org_members"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_organization_members_role",
        "organization_members",
        type_="check",
    )
    op.create_check_constraint(
        "ck_organization_members_role",
        "organization_members",
        "role IN ('OWNER', 'ADMIN', 'EMPLOYEE')",
    )


def downgrade() -> None:
    # A downgrade is intentionally refused by PostgreSQL if ADMIN or EMPLOYEE
    # rows still exist. Silently rewriting them to OWNER would be a privilege
    # escalation; operators must resolve those memberships deliberately first.
    op.drop_constraint(
        "ck_organization_members_role",
        "organization_members",
        type_="check",
    )
    op.create_check_constraint(
        "ck_organization_members_role",
        "organization_members",
        "role IN ('OWNER')",
    )
