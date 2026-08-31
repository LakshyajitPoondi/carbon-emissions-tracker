"""Pydantic schemas for the Organization resource.

Matches docs/api-contract.md — Organizations section.
Response includes the caller's membership role for frontend action gating.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class OrganizationCreate(BaseModel):
    """POST /organizations request body."""
    name: str
    industry_type: str

    @field_validator("name", "industry_type")
    @classmethod
    def must_not_be_empty(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return v.strip()


class OrganizationResponse(BaseModel):
    """POST /organizations and GET /organizations/{id} response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    industry_type: str
    created_at: datetime
    role: Literal["OWNER", "ADMIN", "EMPLOYEE"]
