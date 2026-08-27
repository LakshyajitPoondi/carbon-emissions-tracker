"""Emission Source endpoints.

POST /emission-sources                    — create an emission source
GET  /emission-sources?facility_id={id}   — list emission sources for a facility
"""

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.emission_source import EmissionSource, SourceTypeEnum
from app.models.facility import Facility
from app.schemas.emission_source import EmissionSourceCreate, EmissionSourceResponse
from app.schemas.error import error_response

router = APIRouter(
    prefix="/emission-sources",
    tags=["Emission Sources"],
    dependencies=[Depends(get_current_user)],
)


@router.post(
    "",
    response_model=EmissionSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_emission_source(
    body: EmissionSourceCreate,
    db: Session = Depends(get_db),
):
    # Verify the parent facility exists
    facility = db.get(Facility, body.facility_id)
    if facility is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=error_response(
                "NOT_FOUND",
                f"Facility {body.facility_id} does not exist",
            ),
        )

    if body.barcode_value is not None:
        existing = (
            db.query(EmissionSource)
            .filter(
                EmissionSource.facility_id == body.facility_id,
                EmissionSource.barcode_value == body.barcode_value,
            )
            .first()
        )
        if existing is not None:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content=error_response(
                    "BARCODE_ALREADY_ASSIGNED",
                    f"Barcode '{body.barcode_value}' is already assigned to another "
                    f"emission source in facility {body.facility_id}",
                ),
            )

    source = EmissionSource(
        facility_id=body.facility_id,
        source_type=SourceTypeEnum(body.source_type.value),
        source_name=body.source_name,
        unit_of_measurement=body.unit_of_measurement,
        barcode_value=body.barcode_value,
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get(
    "",
    response_model=list[EmissionSourceResponse],
)
def list_emission_sources(
    facility_id: int = Query(..., description="Filter by facility ID"),
    db: Session = Depends(get_db),
):
    sources = (
        db.query(EmissionSource)
        .filter(EmissionSource.facility_id == facility_id)
        .all()
    )
    return sources
