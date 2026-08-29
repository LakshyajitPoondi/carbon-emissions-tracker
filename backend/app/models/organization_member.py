"""OrganizationMember model — which users may see which organization's data.

This is the table the whole authorization layer rests on. Before it existed,
a valid token was the only gate: any registered user could read and write
every other user's organizations, facilities, records and reports. Every
access check now resolves to "is there a row here for this (user,
organization) pair?" — see app/authorization.py.

Roles: exactly one exists today, OWNER, and no code branches on it. The
column is here so that adding a second role later is a data change rather
than a migration, and it is constrained at the database level so an invalid
role cannot be written even by a direct SQL insert.
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

# The only role that exists. Assigned explicitly at every call site — the
# column deliberately has no default, in database or in Python, so a code
# path that forgets to set it fails loudly on a NOT NULL violation instead
# of silently minting a membership with an implied role.
ROLE_OWNER = "OWNER"

VALID_ROLES = frozenset({ROLE_OWNER})


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
        # Defence in depth: the application only ever writes ROLE_OWNER, but
        # this makes an invalid role unrepresentable regardless of how the
        # row got there.
        CheckConstraint(
            "role IN ('OWNER')", name="ck_organization_members_role"
        ),
        Index("ix_organization_members_user_id", "user_id"),
        Index("ix_organization_members_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<OrganizationMember(user_id={self.user_id}, "
            f"organization_id={self.organization_id}, role={self.role!r})>"
        )
