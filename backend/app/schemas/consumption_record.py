"""Pydantic schemas for the Consumption Record resource.

Matches docs/api-contract.md — Consumption Records section.
POST computes and returns the emissions calculation synchronously — no
separate calculate step in the MVP.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator
from typing import Annotated

from app.models.emission_source import SourceTypeEnum


class ConsumptionRecordCreate(BaseModel):
    """POST /consumption-records request body."""
    emission_source_id: Optional[int] = None
    product_id: Optional[int] = None
    facility_id: int
    quantity_consumed: Decimal
    unit: str
    recorded_at: datetime

    @model_validator(mode="after")
    def validate_selection(self):
        if (self.emission_source_id is None) == (self.product_id is None):
            raise ValueError("Provide exactly one of emission_source_id or product_id")
        if self.product_id is not None:
            TypeAdapter(Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=4)]).validate_python(
                self.quantity_consumed
            )
            if self.recorded_at.tzinfo is None:
                raise ValueError("Product recorded_at must include a timezone")
        return self

    @field_validator("unit")
    @classmethod
    def must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("unit must not be empty")
        return v.strip()


class EmissionCalculationNested(BaseModel):
    """Nested `calculation` object inside a consumption record response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    emission_factor_id: Optional[int]
    calculated_emissions_kg_co2e: Decimal
    calculation_date: date


class ProductConsumptionSnapshot(BaseModel):
    id: int
    name: str
    barcode: Optional[str]
    consumption_unit: str
    consumption_source_type: SourceTypeEnum
    emissions_value: Decimal
    emissions_unit: str
    emissions_description: str
    source_reference: str


class ConsumptionRecordResponse(BaseModel):
    """POST /consumption-records and GET /consumption-records response item.

    No `updated_at` — not part of the contract shape for this resource.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    emission_source_id: Optional[int]
    product_id: Optional[int] = None
    product_snapshot: Optional[ProductConsumptionSnapshot] = None
    facility_id: int
    quantity_consumed: Decimal
    unit: str
    recorded_at: datetime
    created_at: datetime
    calculation: Optional[EmissionCalculationNested] = None
