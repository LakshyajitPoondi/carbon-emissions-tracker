"""Emission Source endpoints.

POST /emission-sources                    — create an emission source
GET  /emission-sources?facility_id={id}   — list emission sources for a facility
GET  /emission-sources/{id}/label         — ZPL label for that source's barcode
"""

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.authorization import (
    OrganizationAction,
    require_emission_source,
    require_facility,
)
from app.database import get_db
from app.models.emission_source import EmissionSource, SourceTypeEnum
from app.models.user import User
from app.schemas.emission_source import EmissionSourceCreate, EmissionSourceResponse
from app.schemas.error import error_response
from app.schemas.label import LabelResponse
from app.services import labels

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
    current_user: User = Depends(get_current_user),
):
    # Replaces the old existence check: a facility in someone else's
    # organization is indistinguishable from one that does not exist.
    require_facility(db, current_user, body.facility_id, OrganizationAction.WRITE)

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
    current_user: User = Depends(get_current_user),
):
    # 404 rather than an empty list: an empty list would still confirm the
    # facility id exists.
    require_facility(db, current_user, facility_id, OrganizationAction.VIEW)

    sources = (
        db.query(EmissionSource)
        .filter(EmissionSource.facility_id == facility_id)
        .all()
    )
    return sources


@router.get(
    "/{emission_source_id}/label",
    response_model=LabelResponse,
)
def get_emission_source_label(
    emission_source_id: int,
    preview: bool = Query(
        True,
        description="Render a PNG preview via the external ZPL renderer. "
        "Set false to skip the outbound call and return ZPL text only.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a printer-ready ZPL label for this source's barcode.

    Nothing is stored: the label is derived from the source on each call,
    so it always reflects the current source name, facility, and barcode.
    """
    # Walks source -> facility -> organization -> membership.
    source = require_emission_source(
        db, current_user, emission_source_id, OrganizationAction.VIEW
    )

    # A label whose barcode field is empty is worse than no label — it
    # looks scannable, prints, and then fails silently at the scanner. Fail
    # loudly here instead, and say what to do about it.
    if not source.barcode_value:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_response(
                "BARCODE_NOT_ASSIGNED",
                f"Emission source {emission_source_id} has no barcode_value, so no "
                f"barcode can be encoded on its label. Assign a barcode to the "
                f"source first, then request the label again.",
            ),
        )

    zpl_code = labels.build_zpl(
        source_name=source.source_name,
        facility_name=source.facility.name,
        source_type=source.source_type.value,
        unit_of_measurement=source.unit_of_measurement,
        barcode_value=source.barcode_value,
    )
    preview_png_base64, preview_note = labels.render_preview(
        zpl_code, requested=preview
    )

    return LabelResponse(
        emission_source_id=source.id,
        barcode_value=source.barcode_value,
        zpl_code=zpl_code,
        label_width_inches=labels.LABEL_WIDTH_INCHES,
        label_height_inches=labels.LABEL_HEIGHT_INCHES,
        print_density_dpmm=labels.PRINT_DENSITY_DPMM,
        preview_png_base64=preview_png_base64,
        preview_note=preview_note,
    )
