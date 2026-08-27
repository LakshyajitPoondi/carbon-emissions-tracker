"""Celery tasks.

Runs in a separate process (celery-worker) from the FastAPI app — never
import app.main here (that would load the FastAPI app object, its CORS
middleware, and the YOLOv8n model, none of which are relevant to running a
task and all of which would waste the worker's startup time). Opens its own
DB session via SessionLocal, since the request-scoped get_db dependency only
exists within a FastAPI request.
"""

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.report import Report, ReportStatusEnum
from app.pubsub import publish_ws_message
from app.services.reports import organization_report_totals


@celery_app.task(name="generate_report")
def generate_report_task(report_id: int) -> None:
    db = SessionLocal()
    try:
        report = db.get(Report, report_id)
        if report is None:
            # Deleted before the task ran — nothing to do. Not an error:
            # the report the task was dispatched for simply no longer
            # exists to update.
            return

        report.status = ReportStatusEnum.PROCESSING
        db.commit()

        total, breakdown = organization_report_totals(
            db, report.organization_id, report.report_period_start, report.report_period_end
        )

        report.total_emissions_kg_co2e = total
        report.facilities_breakdown = [
            {
                "facility_id": item["facility_id"],
                "facility_name": item["facility_name"],
                # JSONB can't store Decimal directly — stringify, matching
                # how the REST API already represents these as decimal
                # strings (e.g. "12045.30"), not floats.
                "total_emissions_kg_co2e": str(item["total_emissions_kg_co2e"]),
            }
            for item in breakdown
        ]
        report.status = ReportStatusEnum.FINAL
        db.commit()
        db.refresh(report)

        publish_ws_message(
            f"organization:{report.organization_id}",
            {
                "type": "report_generated",
                "report": {
                    "id": report.id,
                    "organization_id": report.organization_id,
                    "report_period_start": report.report_period_start.isoformat(),
                    "report_period_end": report.report_period_end.isoformat(),
                    "generated_at": report.generated_at.isoformat(),
                    "status": report.status.value,
                    "total_emissions_kg_co2e": str(report.total_emissions_kg_co2e),
                    "facilities": report.facilities_breakdown,
                },
            },
        )
    finally:
        db.close()
