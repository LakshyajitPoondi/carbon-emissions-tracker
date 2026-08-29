"""Report endpoints.

POST /reports/generate           — create a report (PENDING) and dispatch
                                    async generation; does not block
GET  /reports/{id}                — retrieve a report by ID, whatever its
                                    current status is
GET  /reports?organization_id={id} — list report summaries for an organization
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.authorization import require_organization, require_report
from app.database import get_db
from app.models.user import User
from app.models.report import Report, ReportStatusEnum
from app.schemas.report import (
    ReportDetailResponse,
    ReportGenerateRequest,
    ReportSummaryResponse,
)
from app.tasks import generate_report_task

router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
    dependencies=[Depends(get_current_user)],
)


def _detail_response(report: Report) -> ReportDetailResponse:
    """Reads whatever's currently stored on the row — None for
    total_emissions_kg_co2e/facilities until the Celery task reaches FINAL.
    Never recomputes live; see app/tasks.py for the one place totals are
    actually calculated."""
    return ReportDetailResponse(
        id=report.id,
        organization_id=report.organization_id,
        report_period_start=report.report_period_start,
        report_period_end=report.report_period_end,
        generated_at=report.generated_at,
        status=report.status,
        total_emissions_kg_co2e=report.total_emissions_kg_co2e,
        facilities=report.facilities_breakdown,
    )


@router.post(
    "/generate",
    response_model=ReportDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_report(
    body: ReportGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Reports aggregate an entire organization's emissions — the single most
    # sensitive read in the system, so it is scoped like any other.
    require_organization(db, current_user, body.organization_id)

    report = Report(
        organization_id=body.organization_id,
        report_period_start=body.report_period_start,
        report_period_end=body.report_period_end,
        status=ReportStatusEnum.PENDING,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    generate_report_task.delay(report.id)

    # Deliberately built from `report` as committed above, not re-fetched
    # after dispatch. In production (a real async worker) the task won't
    # have run yet by the time we get here, so the response is PENDING
    # either way — but in Celery's eager-execution test mode, .delay() runs
    # the task synchronously in-process before returning, and a re-fetch
    # here would show FINAL. That would make this endpoint's contract
    # depend on which execution mode happens to be active, which is exactly
    # the kind of thing that passes in tests and lies in production. The
    # response must always reflect "just created," full stop.
    return _detail_response(report)


@router.get(
    "/{report_id}",
    response_model=ReportDetailResponse,
)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Walks report.organization_id -> membership.
    report = require_report(db, current_user, report_id)
    return _detail_response(report)


@router.get(
    "",
    response_model=list[ReportSummaryResponse],
)
def list_reports(
    organization_id: int = Query(..., description="Filter by organization ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_organization(db, current_user, organization_id)

    reports = (
        db.query(Report)
        .filter(Report.organization_id == organization_id)
        .order_by(Report.generated_at.desc())
        .all()
    )
    return [
        ReportSummaryResponse(
            id=report.id,
            organization_id=report.organization_id,
            report_period_start=report.report_period_start,
            report_period_end=report.report_period_end,
            generated_at=report.generated_at,
            status=report.status,
            total_emissions_kg_co2e=report.total_emissions_kg_co2e,
        )
        for report in reports
    ]
