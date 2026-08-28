"""Emissions aggregation for the dashboard summary and report generation.

The dashboard's emissions-summary endpoint always recomputes live (it's
inherently a "right now" view). Reports used to work the same way, but
since async generation (see app/tasks.py) reports now compute their totals
exactly once — via organization_report_totals, called from the Celery task
— and store the result on the `reports` row; GET/list read the stored
values instead of recomputing.
"""

from datetime import date, datetime, time, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.consumption_record import ConsumptionRecord
from app.models.emission_calculation import EmissionCalculation
from app.models.emission_source import EmissionSource, SourceTypeEnum
from app.models.facility import Facility

SUMMARY_QUANT = Decimal("0.01")
ZERO = Decimal("0.00")


def _period_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    """Turn an inclusive [start, end] date range into UTC datetime bounds."""
    start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end, time.max, tzinfo=timezone.utc)
    return start_dt, end_dt


def facility_emissions_by_source_type(
    db: Session, facility_id: int, start: date, end: date
) -> dict[str, Decimal]:
    """Sum kg CO2e for one facility over a period, grouped by source_type.

    Always returns all three source types (ENERGY, FUEL, RESOURCE), defaulting
    to "0.00" for any type with no consumption in the period.
    """
    start_dt, end_dt = _period_bounds(start, end)
    rows = (
        db.query(
            EmissionSource.source_type,
            func.sum(EmissionCalculation.calculated_emissions_kg_co2e),
        )
        .join(ConsumptionRecord, ConsumptionRecord.emission_source_id == EmissionSource.id)
        .join(
            EmissionCalculation,
            EmissionCalculation.consumption_record_id == ConsumptionRecord.id,
        )
        .filter(
            ConsumptionRecord.facility_id == facility_id,
            ConsumptionRecord.recorded_at >= start_dt,
            ConsumptionRecord.recorded_at <= end_dt,
        )
        .group_by(EmissionSource.source_type)
        .all()
    )
    by_type = {
        source_type.value: Decimal(total).quantize(SUMMARY_QUANT, rounding=ROUND_HALF_UP)
        for source_type, total in rows
    }
    for source_type in SourceTypeEnum:
        by_type.setdefault(source_type.value, ZERO)
    return by_type


def facility_total_emissions(db: Session, facility_id: int, start: date, end: date) -> Decimal:
    by_type = facility_emissions_by_source_type(db, facility_id, start, end)
    return sum(by_type.values(), ZERO)


def organization_emissions_by_source_type(
    db: Session, facility_ids: list[int], start: date, end: date
) -> dict[int, dict[str, Decimal]]:
    """Like facility_emissions_by_source_type, but for many facilities in a
    single grouped query instead of one query per facility.

    Added for the GraphQL organization(id) query's nested
    Facility.emissionsSummary field (see app/graphql/): resolving that field
    naively for every facility under an organization would fire one query
    per facility. This groups by (facility_id, source_type) in one query
    instead, then applies the exact same quantization and "default missing
    source types to zero" rules as facility_emissions_by_source_type above,
    reusing its constants (SUMMARY_QUANT, ZERO) so the numbers match REST's
    per-facility endpoint exactly — only the query shape differs, not the
    arithmetic.
    """
    if not facility_ids:
        return {}
    start_dt, end_dt = _period_bounds(start, end)
    rows = (
        db.query(
            ConsumptionRecord.facility_id,
            EmissionSource.source_type,
            func.sum(EmissionCalculation.calculated_emissions_kg_co2e),
        )
        .join(ConsumptionRecord, ConsumptionRecord.emission_source_id == EmissionSource.id)
        .join(
            EmissionCalculation,
            EmissionCalculation.consumption_record_id == ConsumptionRecord.id,
        )
        .filter(
            ConsumptionRecord.facility_id.in_(facility_ids),
            ConsumptionRecord.recorded_at >= start_dt,
            ConsumptionRecord.recorded_at <= end_dt,
        )
        .group_by(ConsumptionRecord.facility_id, EmissionSource.source_type)
        .all()
    )

    result: dict[int, dict[str, Decimal]] = {facility_id: {} for facility_id in facility_ids}
    for facility_id, source_type, total in rows:
        result[facility_id][source_type.value] = Decimal(total).quantize(SUMMARY_QUANT, rounding=ROUND_HALF_UP)
    for facility_id in facility_ids:
        by_type = result[facility_id]
        for source_type in SourceTypeEnum:
            by_type.setdefault(source_type.value, ZERO)
    return result


def organization_report_totals(
    db: Session, organization_id: int, start: date, end: date
) -> tuple[Decimal, list[dict]]:
    """Return (total_emissions, per-facility breakdown) for an organization's period."""
    facilities = db.query(Facility).filter(Facility.organization_id == organization_id).all()
    breakdown = []
    total = ZERO
    for facility in facilities:
        facility_total = facility_total_emissions(db, facility.id, start, end)
        breakdown.append(
            {
                "facility_id": facility.id,
                "facility_name": facility.name,
                "total_emissions_kg_co2e": facility_total,
            }
        )
        total += facility_total
    return total, breakdown
