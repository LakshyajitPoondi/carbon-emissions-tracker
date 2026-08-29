"""Asset Scan endpoint.

POST /facilities/{facility_id}/asset-scan — decode a barcode from an
uploaded webcam frame and resolve it to an emission source in that facility.
"""

from fastapi import APIRouter, Depends, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.authorization import require_facility
from app.models.user import User
from app.database import get_db
from app.ml import get_yolo_model
from app.models.emission_source import EmissionSource
from app.models.facility import Facility
from app.schemas.asset_scan import AssetScanResponse, BoundingBoxResponse
from app.schemas.error import error_response
from app.services.asset_scan import decode_barcode, run_presence_gate

router = APIRouter(prefix="/facilities", tags=["Asset Scan"], dependencies=[Depends(get_current_user)])

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5MB


@router.post(
    "/{facility_id}/asset-scan",
    response_model=AssetScanResponse,
)
async def scan_asset(
    facility_id: int,
    image: UploadFile,
    db: Session = Depends(get_db),
    yolo_model=Depends(get_yolo_model),
    current_user: User = Depends(get_current_user),
):
    # Scanning is scoped to facilities the caller's organization owns.
    require_facility(db, current_user, facility_id)
    facility = db.get(Facility, facility_id)
    if facility is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=error_response("NOT_FOUND", f"Facility {facility_id} does not exist"),
        )

    image_bytes = await image.read()
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_response(
                "VALIDATION_ERROR",
                "image must be a non-empty file no larger than 5MB",
            ),
        )

    decoded = decode_barcode(image_bytes)

    if decoded is None:
        gate = run_presence_gate(yolo_model, image_bytes) if yolo_model is not None else None
        if gate is not None and gate.found:
            message = (
                "An object was detected but no readable barcode was found — "
                "try moving closer or improving lighting"
            )
        else:
            message = "No readable barcode found in frame"
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_response("NO_BARCODE_DETECTED", message),
        )

    source = (
        db.query(EmissionSource)
        .filter(
            EmissionSource.facility_id == facility_id,
            EmissionSource.barcode_value == decoded.value,
        )
        .first()
    )
    if source is None:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_response(
                "BARCODE_NOT_MATCHED",
                f"Barcode '{decoded.value}' does not match any emission source in facility {facility_id}",
            ),
        )

    return AssetScanResponse(
        decoded_value=decoded.value,
        bounding_box=BoundingBoxResponse(
            x=decoded.bounding_box.x,
            y=decoded.bounding_box.y,
            width=decoded.bounding_box.width,
            height=decoded.bounding_box.height,
        ),
        emission_source=source,
    )
