"""Pydantic schemas for the Facility resource.

Matches docs/api-contract.md — Facilities section.
Response includes all create fields + id, created_at, updated_at.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class FacilityCreate(BaseModel):
    """POST /facilities request body."""
    organization_id: int
    name: str
    location: str
    facility_type: str

    @field_validator("name", "location", "facility_type")
    @classmethod
    def must_not_be_empty(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return v.strip()


class FacilityResponse(BaseModel):
    """POST /facilities and GET /facilities response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    name: str
    location: str
    facility_type: str
    created_at: datetime
    updated_at: datetime
