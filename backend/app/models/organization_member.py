"""OrganizationMember model — which users may see which organization's data.

This is the table the whole authorization layer rests on. Before it existed,
a valid token was the only gate: any registered user could read and write
every other user's organizations, facilities, records and reports. Every
access check now resolves to "is there a row here for this (user,
organization) pair?" — see app/authorization.py.

Roles are organization-scoped. OWNER and ADMIN have full access; EMPLOYEE
has read access plus append-only consumption entry. Authorization decisions
live in app/authorization.py rather than on the model, while the database
constraint here makes every other role value unrepresentable.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

ROLE_OWNER = "OWNER"
ROLE_ADMIN = "ADMIN"
ROLE_EMPLOYEE = "EMPLOYEE"

# Assigned explicitly at every call site. The column deliberately has no
# default, in database or in Python, so a code path that forgets to set a
# role fails loudly instead of silently minting an implied permission tier.
VALID_ROLES = frozenset({ROLE_OWNER, ROLE_ADMIN, ROLE_EMPLOYEE})


class OrganizationMember(Base):
    __tablename__ = "organization_members"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # No default, by design — see ROLE_OWNER above.
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User")
    organization = relationship("Organization")

    __table_args__ = (
        # One membership row per user per organization. Also makes
        # "add an existing member again" a database-level no-op rather than
        # a duplicate that quietly doubles every membership query's result.
        UniqueConstraint(
            "user_id", "organization_id", name="uq_organization_members_user_org"
        ),
        # Defence in depth: invalid roles stay unrepresentable regardless of
        # whether a row is written through the application or direct SQL.
        CheckConstraint(
            "role IN ('OWNER', 'ADMIN', 'EMPLOYEE')",
            name="ck_organization_members_role",
        ),
        Index("ix_organization_members_user_id", "user_id"),
        Index("ix_organization_members_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<OrganizationMember(user_id={self.user_id}, "
            f"organization_id={self.organization_id}, role={self.role!r})>"
        )
