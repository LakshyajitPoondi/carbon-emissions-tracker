"""A user's request to become a member of an organization."""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

JOIN_STATUS_PENDING = "PENDING"
JOIN_STATUS_APPROVED = "APPROVED"
JOIN_STATUS_REJECTED = "REJECTED"
VALID_JOIN_STATUSES = frozenset(
    {JOIN_STATUS_PENDING, JOIN_STATUS_APPROVED, JOIN_STATUS_REJECTED}
)


class OrganizationJoinRequest(Base):
    __tablename__ = "organization_join_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    user = relationship("User", foreign_keys=[user_id])
    organization = relationship("Organization")
    decider = relationship("User", foreign_keys=[decided_by])

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_organization_join_requests_status",
        ),
        CheckConstraint(
            "(status = 'PENDING' AND decided_at IS NULL) OR "
            "(status IN ('APPROVED', 'REJECTED') AND decided_at IS NOT NULL)",
            name="ck_organization_join_requests_decision_time",
        ),
        Index(
            "uq_organization_join_requests_pending_user_org",
            "user_id",
            "organization_id",
            unique=True,
            postgresql_where=(status == JOIN_STATUS_PENDING),
        ),
        Index(
            "ix_organization_join_requests_org_status",
            "organization_id",
            "status",
        ),
        Index(
            "ix_organization_join_requests_user_status", "user_id", "status"
        ),
    )

