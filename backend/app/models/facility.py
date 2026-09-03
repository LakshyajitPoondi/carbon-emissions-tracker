"""Facility model — a physical site belonging to an organization."""

from datetime import datetime, timezone

from sqlalchemy import String, Integer, ForeignKey, DateTime, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Facility(Base):
    __tablename__ = "facilities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    facility_type: Mapped[str] = mapped_column(String(100), nullable=False)
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
    organization = relationship("Organization", back_populates="facilities")
    emission_sources = relationship("EmissionSource", back_populates="facility", cascade="all, delete-orphan")
    consumption_records = relationship("ConsumptionRecord", back_populates="facility", cascade="all, delete-orphan", foreign_keys="ConsumptionRecord.facility_id")

    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_facilities_id_organization_id"),
        Index("ix_facilities_organization_id", "organization_id"),
        Index("ix_facilities_name", "name"),
        Index("ix_facilities_facility_type", "facility_type"),
    )

    def __repr__(self) -> str:
        return f"<Facility(id={self.id}, name={self.name!r})>"
