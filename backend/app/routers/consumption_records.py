"""Consumption Record endpoints.

POST /consumption-records — create a record; computes + returns emissions synchronously
GET  /consumption-records?facility_id={id}&start_date=&end_date= — list records for a facility
"""

from datetime import date, datetime, time, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.consumption_record import ConsumptionRecord
from app.models.emission_calculation import EmissionCalculation
from app.models.emission_source import EmissionSource
from app.models.facility import Facility
from app.schemas.consumption_record import ConsumptionRecordCreate, ConsumptionRecordResponse
from app.schemas.error import error_response
from app.services.emissions import (
    DEFAULT_REGION,
    calculate_emissions,
    find_applicable_emission_factor,
)

router = APIRouter(prefix="/consumption-records", tags=["Consumption Records"])


@router.post(
    "",
    response_model=ConsumptionRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_consumption_record(
    body: ConsumptionRecordCreate,
    db: Session = Depends(get_db),
):
    source = db.get(EmissionSource, body.emission_source_id)
    if source is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=error_response(
                "NOT_FOUND",
                f"Emission source {body.emission_source_id} does not exist",
            ),
        )

    facility = db.get(Facility, body.facility_id)
    if facility is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=error_response(
                "NOT_FOUND",
                f"Facility {body.facility_id} does not exist",
            ),
        )

    as_of = body.recorded_at.date()
    factor = find_applicable_emission_factor(db, source.source_type, as_of=as_of)
    if factor is None:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_response(
                "NO_MATCHING_FACTOR",
                f"No emission factor found for source_type={source.source_type.value} "
                f"region={DEFAULT_REGION} as of {as_of.isoformat()}",
            ),
        )

    record = ConsumptionRecord(
        emission_source_id=body.emission_source_id,
        facility_id=body.facility_id,
        quantity_consumed=body.quantity_consumed,
        unit=body.unit,
        recorded_at=body.recorded_at,
    )
    db.add(record)
    db.flush()

    calculation = EmissionCalculation(
        consumption_record_id=record.id,
        emission_factor_id=factor.id,
        calculated_emissions_kg_co2e=calculate_emissions(body.quantity_consumed, factor.factor_value),
        calculation_date=datetime.now(timezone.utc).date(),
    )
    db.add(calculation)
    db.commit()
    db.refresh(record)
    return record


@router.get(
    "",
    response_model=list[ConsumptionRecordResponse],
)
def list_consumption_records(
    facility_id: int = Query(..., description="Filter by facility ID"),
    start_date: Optional[date] = Query(None, description="Inclusive lower bound on recorded_at"),
    end_date: Optional[date] = Query(None, description="Inclusive upper bound on recorded_at"),
    db: Session = Depends(get_db),
):
    query = (
        db.query(ConsumptionRecord)
        .options(joinedload(ConsumptionRecord.emission_calculations))
        .filter(ConsumptionRecord.facility_id == facility_id)
    )
    if start_date is not None:
        query = query.filter(
            ConsumptionRecord.recorded_at >= datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        )
    if end_date is not None:
        query = query.filter(
            ConsumptionRecord.recorded_at <= datetime.combine(end_date, time.max, tzinfo=timezone.utc)
        )
    return query.order_by(ConsumptionRecord.recorded_at).all()
