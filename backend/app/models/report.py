"""Report model — generated emissions reports for an organization."""

import enum
from datetime import date, datetime, timezone

from sqlalchemy import Integer, Date, ForeignKey, DateTime, Enum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ReportStatusEnum(str, enum.Enum):
    """Allowed report statuses."""
    DRAFT = "draft"
    FINAL = "final"


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    report_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    report_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    status: Mapped[ReportStatusEnum] = mapped_column(
        Enum(ReportStatusEnum, name="report_status_enum", create_constraint=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    organization = relationship("Organization", back_populates="reports")

    __table_args__ = (
        Index("ix_reports_organization_id", "organization_id"),
    )

    def __repr__(self) -> str:
        return f"<Report(id={self.id}, status={self.status}, period={self.report_period_start}–{self.report_period_end})>"
