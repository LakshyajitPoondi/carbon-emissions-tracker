"""Organization endpoints.

POST /organizations      — create an organization
GET  /organizations      — list the organizations you are a member of
GET  /organizations/{id} — retrieve an organization by ID
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.authorization import require_organization, user_organization_ids
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
    "",
    response_model=list[OrganizationResponse],
)
def list_organizations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every organization this user is a member of; `[]` if none.

    Membership — not authorship — is what this returns. It deliberately
    delegates to user_organization_ids rather than writing its own join, so
    there is exactly one definition of "belongs to" in the codebase and this
    endpoint cannot drift from the access checks that guard every other
    route. An implementation that filtered on a creator column instead would
    look correct for anyone who made their own organization and silently
    hide organizations shared with them.

    No pagination, deliberately: a membership list is bounded by the number
    of organizations a person has been added to — single digits here, and
    tens in any plausible version of this product. Offset pagination on a
    result set that small costs a second round trip and a page-boundary bug
    class to solve a problem this endpoint does not have. Ordering is stable
    (see below), so pagination can be added later without changing what
    callers already see.
    """
    organization_ids = user_organization_ids(db, current_user)
    if not organization_ids:
        # Skip a query that can only return nothing.
        return []

    # Ordered by name for a predictable picker; id breaks ties, because two
    # organizations may legitimately share a name and "ordered by name"
    # alone would leave their relative order up to the database.
    return (
        db.query(Organization)
        .filter(Organization.id.in_(organization_ids))
        .order_by(Organization.name.asc(), Organization.id.asc())
        .all()
    )


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
