"""EmissionSource model — a specific source of emissions within a facility."""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    String,
    Integer,
    ForeignKey,
    DateTime,
    Index,
    Enum,
    UniqueConstraint,
)
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
    barcode_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
    # foreign_keys is required now that consumption_records has two foreign
    # keys pointing at this table — the plain emission_source_id one and the
    # composite (emission_source_id, facility_id) one added for tenant
    # integrity. Without it SQLAlchemy cannot choose a join condition.
    consumption_records = relationship(
        "ConsumptionRecord",
        back_populates="emission_source",
        cascade="all, delete-orphan",
        foreign_keys="ConsumptionRecord.emission_source_id",
    )

    __table_args__ = (
        # Redundant on its own — id is already unique — but a composite
        # foreign key can only target a uniquely-constrained column pair,
        # and consumption_records references (id, facility_id) to guarantee
        # a record's source and facility belong together. See
        # ConsumptionRecord.__table_args__.
        UniqueConstraint(
            "id", "facility_id", name="uq_emission_sources_id_facility_id"
        ),
        Index("ix_emission_sources_facility_id", "facility_id"),
        Index("ix_emission_sources_source_type", "source_type"),
        Index("ix_emission_sources_source_name", "source_name"),
        Index(
            "ix_emission_sources_facility_id_barcode_value",
            "facility_id",
            "barcode_value",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return f"<EmissionSource(id={self.id}, source_name={self.source_name!r}, type={self.source_type})>"
