"""Organization endpoints.

POST /organizations  — create an organization
GET  /organizations/{id} — retrieve an organization by ID
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.authorization import require_organization
from app.auth import get_current_user
from app.database import get_db
from app.models.organization import Organization
from app.models.organization_member import ROLE_OWNER, OrganizationMember
from app.models.user import User
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
    current_user: User = Depends(get_current_user),
):
    """Creating an organization is what makes you a member of one.

    This is the only way memberships are created. The organization and the
    membership are committed together: flushing the organization first gets
    its generated id, but a single commit means a failure while inserting
    the membership rolls the organization back too. An organization with no
    members would be permanently unreachable by anyone — a row nobody,
    including its creator, could ever read again.
    """
    org = Organization(
        name=body.name,
        industry_type=body.industry_type,
    )
    db.add(org)
    db.flush()  # assigns org.id without ending the transaction

    db.add(
        OrganizationMember(
            user_id=current_user.id,
            organization_id=org.id,
            # Explicit, never defaulted — see app/models/organization_member.py.
            role=ROLE_OWNER,
        )
    )

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
    current_user: User = Depends(get_current_user),
):
    # Raises the same 404 whether the organization is absent or simply not
    # this user's — see app/authorization.py for why they are made
    # indistinguishable.
    return require_organization(db, current_user, organization_id)
