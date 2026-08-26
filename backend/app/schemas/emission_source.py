"""Pydantic schemas for the Emission Source resource.

Matches docs/api-contract.md — Emission Sources section.
source_type must be one of ENERGY, FUEL, RESOURCE (uppercase).
"""

import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class SourceType(str, enum.Enum):
    """Allowed source_type values (API-level enum)."""
    ENERGY = "ENERGY"
    FUEL = "FUEL"
    RESOURCE = "RESOURCE"


class EmissionSourceCreate(BaseModel):
    """POST /emission-sources request body."""
    facility_id: int
    source_type: SourceType
    source_name: str
    unit_of_measurement: str

    @field_validator("source_name", "unit_of_measurement")
    @classmethod
    def must_not_be_empty(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return v.strip()


class EmissionSourceResponse(BaseModel):
    """POST /emission-sources and GET /emission-sources response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    facility_id: int
    source_type: SourceType
    source_name: str
    unit_of_measurement: str
    created_at: datetime
    updated_at: datetime
