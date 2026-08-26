"""Pydantic schemas for the Reports resource.

Matches docs/api-contract.md — Reports section.
total_emissions_kg_co2e and the facilities breakdown are never stored (the
`reports` table has no such columns) — they're computed live by
app/services/reports.py on every generate/get/list call.
"""

import enum
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class ReportStatus(str, enum.Enum):
    """Allowed report statuses (API-level enum, mirrors ReportStatusEnum)."""
    DRAFT = "draft"
    FINAL = "final"


class ReportGenerateRequest(BaseModel):
    """POST /reports/generate request body."""
    organization_id: int
    report_period_start: date
    report_period_end: date


class FacilityBreakdown(BaseModel):
    facility_id: int
    facility_name: str
    total_emissions_kg_co2e: Decimal


class ReportSummaryResponse(BaseModel):
    """GET /reports list item — no nested facilities breakdown."""
    id: int
    organization_id: int
    report_period_start: date
    report_period_end: date
    generated_at: datetime
    status: ReportStatus
    total_emissions_kg_co2e: Decimal


class ReportDetailResponse(ReportSummaryResponse):
    """POST /reports/generate and GET /reports/{id} response."""
    facilities: list[FacilityBreakdown]
