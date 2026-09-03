"""EmissionCalculation model — computed emissions for a consumption record."""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Integer, Numeric, Date, ForeignKey, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EmissionCalculation(Base):
    __tablename__ = "emission_calculations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    consumption_record_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("consumption_records.id", ondelete="CASCADE"), nullable=False
    )
    emission_factor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("emission_factors.id", ondelete="CASCADE"), nullable=True
    )
    calculated_emissions_kg_co2e: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=4), nullable=False
    )
    calculation_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    consumption_record = relationship("ConsumptionRecord", back_populates="emission_calculations")
    emission_factor = relationship("EmissionFactor", back_populates="emission_calculations")

    __table_args__ = (
        Index("ix_emission_calculations_consumption_record_id", "consumption_record_id"),
        Index("ix_emission_calculations_emission_factor_id", "emission_factor_id"),
    )

    def __repr__(self) -> str:
        return f"<EmissionCalculation(id={self.id}, kg_co2e={self.calculated_emissions_kg_co2e})>"
