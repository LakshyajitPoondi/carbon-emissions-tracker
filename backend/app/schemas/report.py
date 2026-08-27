"""Pydantic schemas for the Reports resource.

Matches docs/api-contract.md — Reports section. total_emissions_kg_co2e and
facilities are populated once by the Celery task (app/tasks.py) when a
report reaches FINAL, and stored on the row from then on — not recomputed
live on every read. Both are None while PENDING/PROCESSING.
"""

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class ReportStatus(str, enum.Enum):
    """Allowed report statuses (API-level enum, mirrors ReportStatusEnum)."""
    DRAFT = "draft"
    PENDING = "pending"
    PROCESSING = "processing"
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
    total_emissions_kg_co2e: Optional[Decimal] = None


class ReportDetailResponse(ReportSummaryResponse):
    """POST /reports/generate and GET /reports/{id} response."""
    facilities: Optional[list[FacilityBreakdown]] = None
