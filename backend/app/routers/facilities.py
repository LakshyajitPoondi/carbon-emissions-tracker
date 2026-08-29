"""Facility endpoints.

POST /facilities                              — create a facility
GET  /facilities?organization_id={id}         — list facilities for an organization
GET  /facilities/{id}/emissions-summary        — dashboard emissions summary
"""

from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.authorization import require_facility, require_organization
from app.database import get_db
from app.models.facility import Facility
from app.models.user import User
from app.schemas.emissions_summary import EmissionsSummaryResponse
from app.schemas.facility import FacilityCreate, FacilityResponse
from app.services.reports import facility_emissions_by_source_type

router = APIRouter(
    prefix="/facilities",
    tags=["Facilities"],
    dependencies=[Depends(get_current_user)],
)


@router.post(
    "",
    response_model=FacilityResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_facility(
    body: FacilityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Replaces the old existence check: a parent organization the caller is
    # not a member of is indistinguishable from one that does not exist.
    require_organization(db, current_user, body.organization_id)

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
    current_user: User = Depends(get_current_user),
):
    # Authorize the organization before listing, so a non-member gets a 404
    # rather than an empty list — an empty list would still confirm the
    # organization id is valid.
    require_organization(db, current_user, organization_id)

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
    current_user: User = Depends(get_current_user),
):
    require_facility(db, current_user, facility_id)

    by_source_type = facility_emissions_by_source_type(db, facility_id, start_date, end_date)
    total = sum(by_source_type.values())

    return EmissionsSummaryResponse(
        facility_id=facility_id,
        period={"start": start_date, "end": end_date},
        total_emissions_kg_co2e=total,
        by_source_type=by_source_type,
    )
