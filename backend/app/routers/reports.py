"""Report endpoints.

POST /reports/generate           — generate a report for an organization/period
GET  /reports/{id}                — retrieve a report by ID (recomputed live)
GET  /reports?organization_id={id} — list report summaries for an organization
"""

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.organization import Organization
from app.models.report import Report, ReportStatusEnum
from app.schemas.error import error_response
from app.schemas.report import (
    ReportDetailResponse,
    ReportGenerateRequest,
    ReportSummaryResponse,
)
from app.services.reports import organization_report_totals

router = APIRouter(prefix="/reports", tags=["Reports"])


def _detail_response(report: Report, db: Session) -> ReportDetailResponse:
    total, breakdown = organization_report_totals(
        db, report.organization_id, report.report_period_start, report.report_period_end
    )
    return ReportDetailResponse(
        id=report.id,
        organization_id=report.organization_id,
        report_period_start=report.report_period_start,
        report_period_end=report.report_period_end,
        generated_at=report.generated_at,
        status=report.status,
        total_emissions_kg_co2e=total,
        facilities=breakdown,
    )


@router.post(
    "/generate",
    response_model=ReportDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_report(
    body: ReportGenerateRequest,
    db: Session = Depends(get_db),
):
    org = db.get(Organization, body.organization_id)
    if org is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=error_response(
                "NOT_FOUND",
                f"Organization {body.organization_id} does not exist",
            ),
        )

    report = Report(
        organization_id=body.organization_id,
        report_period_start=body.report_period_start,
        report_period_end=body.report_period_end,
        status=ReportStatusEnum.FINAL,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return _detail_response(report, db)


@router.get(
    "/{report_id}",
    response_model=ReportDetailResponse,
)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
):
    report = db.get(Report, report_id)
    if report is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=error_response(
                "NOT_FOUND",
                f"Report {report_id} does not exist",
            ),
        )
    return _detail_response(report, db)


@router.get(
    "",
    response_model=list[ReportSummaryResponse],
)
def list_reports(
    organization_id: int = Query(..., description="Filter by organization ID"),
    db: Session = Depends(get_db),
):
    reports = (
        db.query(Report)
        .filter(Report.organization_id == organization_id)
        .order_by(Report.generated_at.desc())
        .all()
    )
    summaries = []
    for report in reports:
        total, _breakdown = organization_report_totals(
            db, report.organization_id, report.report_period_start, report.report_period_end
        )
        summaries.append(
            ReportSummaryResponse(
                id=report.id,
                organization_id=report.organization_id,
                report_period_start=report.report_period_start,
                report_period_end=report.report_period_end,
                generated_at=report.generated_at,
                status=report.status,
                total_emissions_kg_co2e=total,
            )
        )
    return summaries
