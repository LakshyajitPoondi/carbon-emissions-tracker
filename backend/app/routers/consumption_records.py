"""Consumption Record endpoints.

POST /consumption-records — create a record; computes + returns emissions synchronously
GET  /consumption-records?facility_id={id}&start_date=&end_date= — list records for a facility
"""

from datetime import date, datetime, time, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user
from app.authorization import require_emission_source, require_facility
from app.database import get_db
from app.models.consumption_record import ConsumptionRecord
from app.models.emission_calculation import EmissionCalculation
from app.models.user import User
from app.schemas.consumption_record import ConsumptionRecordCreate, ConsumptionRecordResponse
from app.schemas.error import error_response
from app.services.emissions import (
    DEFAULT_REGION,
    calculate_emissions,
    find_applicable_emission_factor,
)
from app.ws import manager

router = APIRouter(
    prefix="/consumption-records",
    tags=["Consumption Records"],
    dependencies=[Depends(get_current_user)],
)


@router.post(
    "",
    response_model=ConsumptionRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_consumption_record(
    body: ConsumptionRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Both the source and the facility must belong to an organization this
    # user is a member of. Checked independently, because owning one does
    # not imply owning the other.
    source = require_emission_source(db, current_user, body.emission_source_id)
    require_facility(db, current_user, body.facility_id)

    # ...and they must belong to each other. Passing both checks above still
    # allows pairing your own facility with a source from a different
    # facility — including one in another organization — which would file
    # that source's identity into your records and corrupt every downstream
    # total. The database enforces this too (composite foreign key, see
    # app/models/consumption_record.py); this check exists so the caller
    # gets a documented 422 instead of an IntegrityError surfacing as a 500.
    if source.facility_id != body.facility_id:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_response(
                "SOURCE_FACILITY_MISMATCH",
                f"Emission source {body.emission_source_id} belongs to facility "
                f"{source.facility_id}, not facility {body.facility_id}",
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

    # Broadcast the full record (not a pre-aggregated summary total) to
    # every WebSocket client watching this facility. The server has no way
    # to know which date range each connected dashboard currently has
    # selected, so it can't correctly compute "the new total" on their
    # behalf — sending the raw record lets the frontend decide whether/how
    # to fold it in (refetch the summary, or bump a locally-held total only
    # if this record's recorded_at falls within the currently-viewed
    # period). See docs/api-contract.md's WebSocket section for the same
    # reasoning written out for the frontend side.
    response = ConsumptionRecordResponse.model_validate(record)
    await manager.broadcast(
        f"facility:{body.facility_id}",
        {
            "type": "consumption_record_created",
            "consumption_record": response.model_dump(mode="json"),
        },
    )

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
    current_user: User = Depends(get_current_user),
):
    require_facility(db, current_user, facility_id)

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
