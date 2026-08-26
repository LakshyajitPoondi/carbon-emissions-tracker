"""Facility endpoints.

POST /facilities                              — create a facility
GET  /facilities?organization_id={id}         — list facilities for an organization
GET  /facilities/{id}/emissions-summary        — dashboard emissions summary
"""

from datetime import date

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.facility import Facility
from app.models.organization import Organization
from app.schemas.emissions_summary import EmissionsSummaryResponse
from app.schemas.error import error_response
from app.schemas.facility import FacilityCreate, FacilityResponse
from app.services.reports import facility_emissions_by_source_type

router = APIRouter(prefix="/facilities", tags=["Facilities"])


@router.post(
    "",
    response_model=FacilityResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_facility(
    body: FacilityCreate,
    db: Session = Depends(get_db),
):
    # Verify the parent organization exists
    org = db.get(Organization, body.organization_id)
    if org is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=error_response(
                "NOT_FOUND",
                f"Organization {body.organization_id} does not exist",
            ),
        )

    facility = Facility(
        organization_id=body.organization_id,
        name=body.name,
        location=body.location,
        facility_type=body.facility_type,
    )
    db.add(facility)
    db.commit()
    db.refresh(facility)
    return facility


@router.get(
    "",
    response_model=list[FacilityResponse],
)
def list_facilities(
    organization_id: int = Query(..., description="Filter by organization ID"),
    db: Session = Depends(get_db),
):
    facilities = (
        db.query(Facility)
        .filter(Facility.organization_id == organization_id)
        .all()
    )
    return facilities


@router.get(
    "/{facility_id}/emissions-summary",
    response_model=EmissionsSummaryResponse,
)
def get_emissions_summary(
    facility_id: int,
    start_date: date = Query(..., description="Inclusive period start"),
    end_date: date = Query(..., description="Inclusive period end"),
    db: Session = Depends(get_db),
):
    facility = db.get(Facility, facility_id)
    if facility is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=error_response(
                "NOT_FOUND",
                f"Facility {facility_id} does not exist",
            ),
        )

    by_source_type = facility_emissions_by_source_type(db, facility_id, start_date, end_date)
    total = sum(by_source_type.values())

    return EmissionsSummaryResponse(
        facility_id=facility_id,
        period={"start": start_date, "end": end_date},
        total_emissions_kg_co2e=total,
        by_source_type=by_source_type,
    )
