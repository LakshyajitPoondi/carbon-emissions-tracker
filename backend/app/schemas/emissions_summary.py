"""Pydantic schema for the facility emissions-summary (dashboard) endpoint.

Matches docs/api-contract.md — Emissions Summary section.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class EmissionsPeriod(BaseModel):
    start: date
    end: date


class EmissionsSummaryResponse(BaseModel):
    """GET /facilities/{id}/emissions-summary response."""
    facility_id: int
    period: EmissionsPeriod
    total_emissions_kg_co2e: Decimal
    by_source_type: dict[str, Decimal]
