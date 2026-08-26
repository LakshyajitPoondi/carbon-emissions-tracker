"""Pydantic schemas for the Consumption Record resource.

Matches docs/api-contract.md — Consumption Records section.
POST computes and returns the emissions calculation synchronously — no
separate calculate step in the MVP.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class ConsumptionRecordCreate(BaseModel):
    """POST /consumption-records request body."""
    emission_source_id: int
    facility_id: int
    quantity_consumed: Decimal
    unit: str
    recorded_at: datetime

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
    emission_factor_id: int
    calculated_emissions_kg_co2e: Decimal
    calculation_date: date


class ConsumptionRecordResponse(BaseModel):
    """POST /consumption-records and GET /consumption-records response item.

    No `updated_at` — not part of the contract shape for this resource.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    emission_source_id: int
    facility_id: int
    quantity_consumed: Decimal
    unit: str
    recorded_at: datetime
    created_at: datetime
    calculation: Optional[EmissionCalculationNested] = None
