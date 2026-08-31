"""Pydantic schemas for the Emission Source resource.

Matches docs/api-contract.md — Emission Sources section.
source_type must be one of ENERGY, FUEL, RESOURCE (uppercase).
"""

import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SourceType(str, enum.Enum):
    """Allowed source_type values (API-level enum)."""
    ENERGY = "ENERGY"
    FUEL = "FUEL"
    RESOURCE = "RESOURCE"


class EmissionSourceCreate(BaseModel):
    """POST /emission-sources request body."""
    facility_id: int
    source_type: SourceType
    source_name: str = Field(max_length=255)
    unit_of_measurement: str = Field(max_length=50)
    barcode_value: Optional[str] = Field(default=None, max_length=255)

    @field_validator("source_name", "unit_of_measurement")
    @classmethod
    def must_not_be_empty(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return v.strip()

    @field_validator("barcode_value")
    @classmethod
    def barcode_value_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        return v or None


class EmissionSourceUpdate(BaseModel):
    """PATCH /emission-sources/{id}; facility ownership is immutable."""

    source_type: Optional[SourceType] = None
    source_name: Optional[str] = Field(default=None, max_length=255)
    unit_of_measurement: Optional[str] = Field(default=None, max_length=50)
    barcode_value: Optional[str] = Field(default=None, max_length=255)

    @field_validator("source_name", "unit_of_measurement")
    @classmethod
    def updated_text_not_blank(cls, v: Optional[str], info) -> Optional[str]:
        if v is None:
            return None
        if not v.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return v.strip()

    @field_validator("barcode_value")
    @classmethod
    def normalize_barcode(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v.strip() or None

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("at least one emission source field must be provided")
        for field_name in self.model_fields_set - {"barcode_value"}:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} may not be null")
        return self


class EmissionSourceResponse(BaseModel):
    """Create, update, and list response shape."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    facility_id: int
    source_type: SourceType
    source_name: str
    unit_of_measurement: str
    barcode_value: Optional[str] = None
    created_at: datetime
    updated_at: datetime
