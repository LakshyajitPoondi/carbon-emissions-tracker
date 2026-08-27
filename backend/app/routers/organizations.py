"""Organization endpoints.

POST /organizations  — create an organization
GET  /organizations/{id} — retrieve an organization by ID
"""

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.organization import Organization
from app.schemas.error import error_response
from app.schemas.organization import OrganizationCreate, OrganizationResponse

router = APIRouter(
    prefix="/organizations",
    tags=["Organizations"],
    dependencies=[Depends(get_current_user)],
)


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_organization(
    body: OrganizationCreate,
    db: Session = Depends(get_db),
):
    org = Organization(
        name=body.name,
        industry_type=body.industry_type,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@router.get(
    "/{organization_id}",
    response_model=OrganizationResponse,
)
def get_organization(
    organization_id: int,
    db: Session = Depends(get_db),
):
    org = db.get(Organization, organization_id)
    if org is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=error_response(
                "NOT_FOUND",
                f"Organization {organization_id} does not exist",
            ),
        )
    return org
