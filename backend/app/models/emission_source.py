"""EmissionSource model — a specific source of emissions within a facility."""

import enum
from datetime import datetime, timezone

from sqlalchemy import String, Integer, ForeignKey, DateTime, Index, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SourceTypeEnum(str, enum.Enum):
    """Allowed emission source types."""
    ENERGY = "ENERGY"
    FUEL = "FUEL"
    RESOURCE = "RESOURCE"


class EmissionSource(Base):
    __tablename__ = "emission_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    facility_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[SourceTypeEnum] = mapped_column(
        Enum(SourceTypeEnum, name="source_type_enum", create_constraint=True),
        nullable=False,
    )
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_of_measurement: Mapped[str] = mapped_column(String(50), nullable=False)
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
    facility = relationship("Facility", back_populates="emission_sources")
    consumption_records = relationship("ConsumptionRecord", back_populates="emission_source", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_emission_sources_facility_id", "facility_id"),
        Index("ix_emission_sources_source_type", "source_type"),
        Index("ix_emission_sources_source_name", "source_name"),
    )

    def __repr__(self) -> str:
        return f"<EmissionSource(id={self.id}, source_name={self.source_name!r}, type={self.source_type})>"
