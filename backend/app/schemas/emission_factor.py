"""Pydantic schemas for the Emission Factor resource.

Matches docs/api-contract.md — Emission Factors section.
Read-only in the MVP: seeded via app/seed.py, never created through the API.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class EmissionFactorResponse(BaseModel):
    """GET /emission-factors response item."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: str
    region: str
    factor_value: Decimal
    unit: str
    valid_from: date
    valid_to: Optional[date]
    source_reference: str
