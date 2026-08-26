"""ConsumptionRecord model — tracks resource consumption at a facility."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Integer, Numeric, ForeignKey, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ConsumptionRecord(Base):
    __tablename__ = "consumption_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    emission_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("emission_sources.id", ondelete="CASCADE"), nullable=False
    )
    facility_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    quantity_consumed: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=4), nullable=False
    )
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    recorded_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
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
    emission_source = relationship("EmissionSource", back_populates="consumption_records")
    facility = relationship("Facility", back_populates="consumption_records")
    emission_calculations = relationship("EmissionCalculation", back_populates="consumption_record", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_consumption_records_emission_source_id", "emission_source_id"),
        Index("ix_consumption_records_facility_id", "facility_id"),
    )

    @property
    def calculation(self) -> Optional["EmissionCalculation"]:
        """Single nested calculation for API responses.

        The MVP computes emissions synchronously at creation, so there is
        exactly one calculation per record — this exposes it as a scalar
        (or None) instead of the underlying one-to-many relationship, to
        match the `calculation` field in docs/api-contract.md.
        """
        return self.emission_calculations[0] if self.emission_calculations else None

    def __repr__(self) -> str:
        return f"<ConsumptionRecord(id={self.id}, quantity={self.quantity_consumed}, unit={self.unit!r})>"
