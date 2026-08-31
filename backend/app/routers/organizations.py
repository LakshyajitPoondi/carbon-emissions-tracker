"""Organization endpoints.

POST /organizations      — create an organization
GET  /organizations      — list the organizations you are a member of
GET  /organizations/{id} — retrieve an organization by ID
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.authorization import (
    OrganizationAction,
    organization_role,
    require_organization,
)
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


def _organization_response(
    organization: Organization, role: str
) -> OrganizationResponse:
    """Attach the requester's membership role to the organization resource."""
    return OrganizationResponse(
        id=organization.id,
        name=organization.name,
        industry_type=organization.industry_type,
        created_at=organization.created_at,
        role=role,
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
    return _organization_response(org, ROLE_OWNER)


@router.get(
    "",
    response_model=list[OrganizationResponse],
)
def list_organizations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every organization this user is a member of; `[]` if none.

    Membership — not authorship — is what this returns. The join also carries
    each membership's role so the response can expose the caller's role for
    that specific organization.

    No pagination, deliberately: a membership list is bounded by the number
    of organizations a person has been added to — single digits here, and
    tens in any plausible version of this product. Offset pagination on a
    result set that small costs a second round trip and a page-boundary bug
    class to solve a problem this endpoint does not have. Ordering is stable
    (see below), so pagination can be added later without changing what
    callers already see.
    """
    # Ordered by name for a predictable picker; id breaks ties, because two
    # organizations may legitimately share a name and "ordered by name"
    # alone would leave their relative order up to the database.
    rows = (
        db.query(Organization, OrganizationMember.role)
        .join(
            OrganizationMember,
            OrganizationMember.organization_id == Organization.id,
        )
        .filter(OrganizationMember.user_id == current_user.id)
        .order_by(Organization.name.asc(), Organization.id.asc())
        .all()
    )
    return [_organization_response(organization, role) for organization, role in rows]


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
    organization = require_organization(
        db, current_user, organization_id, OrganizationAction.VIEW
    )
    role = organization_role(db, current_user.id, organization_id)
    # require_organization just proved this membership exists.
    assert role is not None
    return _organization_response(organization, role)
