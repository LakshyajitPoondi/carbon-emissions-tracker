"""EmissionFactor model — reference data for converting activity to CO₂e."""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Numeric, Date, DateTime, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EmissionFactor(Base):
    __tablename__ = "emission_factors"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    factor_value: Mapped[Decimal] = mapped_column(
        Numeric(precision=12, scale=6), nullable=False
    )
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    source_reference: Mapped[str] = mapped_column(Text, nullable=False)
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
    emission_calculations = relationship("EmissionCalculation", back_populates="emission_factor", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_emission_factors_source_type", "source_type"),
        Index("ix_emission_factors_region", "region"),
        Index("ix_emission_factors_source_type_region", "source_type", "region"),
    )

    def __repr__(self) -> str:
        return f"<EmissionFactor(id={self.id}, source_type={self.source_type!r}, region={self.region!r})>"
