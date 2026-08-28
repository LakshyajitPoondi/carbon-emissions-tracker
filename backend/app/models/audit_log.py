"""AuditLog model — one row per audited write request.

Written by app/middleware/audit.py, never by a route handler: auditing that
depends on every endpoint remembering to call a helper is auditing that
silently stops covering the endpoint someone forgets. Read back through
GET /api/audit-logs (app/routers/audit_logs.py).
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Nullable, and ON DELETE SET NULL rather than CASCADE: an audit trail
    # that deletes itself when the acting user is removed is not an audit
    # trail. Null also covers genuinely unauthenticated writes — a request
    # rejected with 401 before any user was resolved still gets logged, and
    # that attempt is exactly the kind of thing worth keeping.
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # "CREATE" | "UPDATE" | "DELETE", derived from the HTTP method.
    action: Mapped[str] = mapped_column(String(16), nullable=False)

    # Singular snake_case resource name derived from the URL path
    # ("organization", "consumption_record"). See app/middleware/audit.py.
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)

    # Null whenever the path carries no id — every POST-to-a-collection, so
    # most creates. See the "Known limitations" note in the API contract.
    resource_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User")

    __table_args__ = (
        # timestamp: the list endpoint's ORDER BY. The other two back the
        # two documented query filters.
        Index("ix_audit_logs_timestamp", "timestamp"),
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_resource_type", "resource_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id}, action={self.action!r}, "
            f"resource_type={self.resource_type!r}, status_code={self.status_code})>"
        )
