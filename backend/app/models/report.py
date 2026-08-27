"""Report model — generated emissions reports for an organization."""

import enum
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Integer, Date, ForeignKey, DateTime, Enum, Index, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ReportStatusEnum(str, enum.Enum):
    """Allowed report statuses. PENDING/PROCESSING exist for async
    generation (see app/tasks.py) — a report is created PENDING, the Celery
    task flips it to PROCESSING while it aggregates, then FINAL once
    total_emissions_kg_co2e/facilities_breakdown are populated. DRAFT
    predates async generation and isn't part of that flow; kept as-is since
    nothing asked to remove it."""
    DRAFT = "draft"
    PENDING = "pending"
    PROCESSING = "processing"
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
    # Both null until the Celery task reaches FINAL — see app/tasks.py.
    # Stored (not recomputed live) so a generated report is a stable
    # snapshot, not something that silently changes number on every read.
    # scale=2 matches SUMMARY_QUANT in app/services/reports.py, which is
    # what actually produces this value ("708.20", not "708.2000").
    total_emissions_kg_co2e: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(precision=14, scale=2), nullable=True
    )
    facilities_breakdown: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
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
