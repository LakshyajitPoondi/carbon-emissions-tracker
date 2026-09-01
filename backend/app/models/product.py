"""Organization-scoped manually maintained product reference data."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Nullable on purpose: a product may be catalogued before its barcode is
    # known. PostgreSQL permits multiple NULLs under the unique constraint.
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True)
    barcode_image: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    composition: Mapped[str] = mapped_column(Text, nullable=False)
    emissions_value: Mapped[Decimal] = mapped_column(
        Numeric(precision=18, scale=6), nullable=False
    )
    emissions_unit: Mapped[str] = mapped_column(String(100), nullable=False)
    emissions_description: Mapped[str] = mapped_column(Text, nullable=False)
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

    organization = relationship("Organization", back_populates="products")

    __table_args__ = (
        # The same real-world SKU can appear in separate organizations'
        # libraries. Within one organization a non-null barcode identifies a
        # single product; NULL remains repeatable for not-yet-known barcodes.
        UniqueConstraint(
            "organization_id",
            "barcode",
            name="uq_products_organization_barcode",
        ),
        CheckConstraint(
            "emissions_value >= 0", name="ck_products_emissions_nonnegative"
        ),
        Index("ix_products_organization_id", "organization_id"),
        Index("ix_products_name", "name"),
    )

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name={self.name!r}, barcode={self.barcode!r})>"
