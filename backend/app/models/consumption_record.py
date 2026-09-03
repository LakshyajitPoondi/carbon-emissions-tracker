"""ConsumptionRecord model — tracks resource consumption at a facility."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    String,
    Integer,
    Numeric,
    ForeignKey,
    ForeignKeyConstraint,
    DateTime,
    Index,
    JSON,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ConsumptionRecord(Base):
    __tablename__ = "consumption_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    emission_source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("emission_sources.id", ondelete="CASCADE"), nullable=True
    )
    # Composite FKs below enforce product/facility tenant consistency.
    # The product link may disappear on deletion; the snapshot never does.
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_organization_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_snapshot: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    product_source_type: Mapped[str | None] = mapped_column(String(8), nullable=True)
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
    emission_source = relationship(
        "EmissionSource",
        back_populates="consumption_records",
        # Disambiguates against the composite foreign key below, which also
        # targets emission_sources.
        foreign_keys=[emission_source_id],
    )
    facility = relationship("Facility", back_populates="consumption_records", foreign_keys=[facility_id])
    emission_calculations = relationship("EmissionCalculation", back_populates="consumption_record", cascade="all, delete-orphan")

    __table_args__ = (
        ForeignKeyConstraint(
            ["product_id", "product_organization_id"],
            ["products.id", "products.organization_id"],
            name="fk_consumption_records_product_organization",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["facility_id", "product_organization_id"],
            ["facilities.id", "facilities.organization_id"],
            name="fk_consumption_records_product_facility_organization",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "(emission_source_id IS NOT NULL AND product_id IS NULL "
            "AND product_organization_id IS NULL AND product_snapshot IS NULL "
            "AND product_source_type IS NULL) OR "
            "(emission_source_id IS NULL AND product_snapshot IS NOT NULL "
            "AND product_source_type IS NOT NULL "
            "AND product_source_type IN ('ENERGY', 'FUEL', 'RESOURCE') "
            "AND ((product_id IS NULL AND product_organization_id IS NULL) OR "
            "(product_id IS NOT NULL AND product_organization_id IS NOT NULL)))",
            name="ck_consumption_records_source_or_product",
        ),
        Index("ix_consumption_records_product_id", "product_id"),
        # Tenant integrity, enforced by the database rather than by the
        # handler alone: a record's emission source must belong to the very
        # facility the record is filed against. Without this, an
        # application-level check is the only thing standing between a
        # caller and a record that joins their own facility to another
        # organization's emission source — and any code path that writes a
        # record without repeating that check (a script, a future endpoint,
        # a bulk import) silently reopens the hole. Targets the composite
        # unique constraint on emission_sources(id, facility_id).
        ForeignKeyConstraint(
            ["emission_source_id", "facility_id"],
            ["emission_sources.id", "emission_sources.facility_id"],
            name="fk_consumption_records_source_facility",
            ondelete="CASCADE",
        ),
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
