"""Object-level authorization: does this user get to touch this row?

Authentication (app/auth.py) answers "who is this?". This module answers
"is this theirs?" — the question that was missing, and whose absence let any
registered user read and write every other user's data through REST,
GraphQL, and WebSockets alike.

Every resource resolves to an organization, either directly
(organizations, reports) or by walking foreign keys
(emission_sources -> facilities -> organization). Access is then answered
by one membership row and one centrally defined action matrix: VIEW, ENTRY,
or WRITE.

Two deliberate design choices
-----------------------------
**Plain functions, not FastAPI dependencies.** They return the loaded object
so handlers do not re-query it, and — the deciding reason — GraphQL
resolvers and WebSocket handlers are outside the REST dependency tree and
need the same checks. One implementation serves all three.

**Absent and inaccessible are indistinguishable.** Each helper expresses the
membership requirement as a join, so a row belonging to someone else simply
does not come back, and the same 404 is raised with the same message as for
a row that never existed. This is not laziness about error messages: with
sequential integer ids and open registration, a 403 would confirm which ids
exist and let anyone map the entire object graph. The masking is the point,
and it falls out of the query shape rather than depending on two error
strings being kept in sync.
"""

from enum import Enum

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.emission_source import EmissionSource
from app.models.facility import Facility
from app.models.organization import Organization
from app.models.organization_member import (
    ROLE_ADMIN,
    ROLE_EMPLOYEE,
    ROLE_OWNER,
    OrganizationMember,
)
from app.models.report import Report
from app.models.user import User


def _not_found(resource: str, resource_id: int) -> HTTPException:
    """The single 404 every denial and every genuine miss share.

    Wording matches what the handlers already returned before authorization
    existed, so the contract's error messages are unchanged.
    """
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "NOT_FOUND",
            "message": f"{resource} {resource_id} does not exist",
        },
    )


class OrganizationAction(str, Enum):
    """Organization-scoped actions understood by the role matrix.

    VIEW covers every read-only REST/GraphQL/WebSocket path. ENTRY is the
    deliberately narrow append-only permission to create a consumption
    record. WRITE covers every other mutation that exists today.
    """

    VIEW = "VIEW"
    ENTRY = "ENTRY"
    WRITE = "WRITE"


_ROLES_BY_ACTION = {
    OrganizationAction.VIEW: frozenset({ROLE_OWNER, ROLE_ADMIN, ROLE_EMPLOYEE}),
    OrganizationAction.ENTRY: frozenset({ROLE_OWNER, ROLE_ADMIN, ROLE_EMPLOYEE}),
    OrganizationAction.WRITE: frozenset({ROLE_OWNER, ROLE_ADMIN}),
}


def role_allows(role: str, action: OrganizationAction) -> bool:
    """Pure role-matrix check, shared by request authorization and tests."""
    return role in _ROLES_BY_ACTION[action]


def has_organization_access(
    db: Session,
    user_id: int,
    organization_id: int,
    action: OrganizationAction = OrganizationAction.WRITE,
) -> bool:
    """Whether a membership grants ``action`` in an organization.

    WRITE is the deliberately restrictive default: a future call site that
    does not classify its action never grants EMPLOYEE access by accident.
    """
    return (
        db.query(OrganizationMember.id)
        .filter(
            OrganizationMember.user_id == user_id,
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.role.in_(_ROLES_BY_ACTION[action]),
        )
        .first()
        is not None
    )


def organization_role(
    db: Session, user_id: int, organization_id: int
) -> str | None:
    """The caller's role in an organization, or None without membership."""
    row = (
        db.query(OrganizationMember.role)
        .filter(
            OrganizationMember.user_id == user_id,
            OrganizationMember.organization_id == organization_id,
        )
        .first()
    )
    return row[0] if row is not None else None


def require_organization(
    db: Session,
    user: User,
    organization_id: int,
    action: OrganizationAction = OrganizationAction.WRITE,
) -> Organization:
    """An organization the user's role may perform ``action`` on, else 404."""
    organization = (
        db.query(Organization)
        .join(
            OrganizationMember,
            OrganizationMember.organization_id == Organization.id,
        )
        .filter(
            Organization.id == organization_id,
            OrganizationMember.user_id == user.id,
            OrganizationMember.role.in_(_ROLES_BY_ACTION[action]),
        )
        .first()
    )
    if organization is None:
        raise _not_found("Organization", organization_id)
    return organization


def require_facility(
    db: Session,
    user: User,
    facility_id: int,
    action: OrganizationAction = OrganizationAction.WRITE,
) -> Facility:
    """A facility the user's organization role permits ``action`` on."""
    facility = (
        db.query(Facility)
        .join(
            OrganizationMember,
            OrganizationMember.organization_id == Facility.organization_id,
        )
        .filter(
            Facility.id == facility_id,
            OrganizationMember.user_id == user.id,
            OrganizationMember.role.in_(_ROLES_BY_ACTION[action]),
        )
        .first()
    )
    if facility is None:
        raise _not_found("Facility", facility_id)
    return facility


def require_emission_source(
    db: Session,
    user: User,
    emission_source_id: int,
    action: OrganizationAction = OrganizationAction.WRITE,
) -> EmissionSource:
    """A source the user's organization role permits ``action`` on."""
    source = (
        db.query(EmissionSource)
        .join(Facility, Facility.id == EmissionSource.facility_id)
        .join(
            OrganizationMember,
            OrganizationMember.organization_id == Facility.organization_id,
        )
        .filter(
            EmissionSource.id == emission_source_id,
            OrganizationMember.user_id == user.id,
            OrganizationMember.role.in_(_ROLES_BY_ACTION[action]),
        )
        .first()
    )
    if source is None:
        raise _not_found("Emission source", emission_source_id)
    return source


def require_report(
    db: Session,
    user: User,
    report_id: int,
    action: OrganizationAction = OrganizationAction.WRITE,
) -> Report:
    """A report the user's organization role permits ``action`` on."""
    report = (
        db.query(Report)
        .join(
            OrganizationMember,
            OrganizationMember.organization_id == Report.organization_id,
        )
        .filter(
            Report.id == report_id,
            OrganizationMember.user_id == user.id,
            OrganizationMember.role.in_(_ROLES_BY_ACTION[action]),
        )
        .first()
    )
    if report is None:
        raise _not_found("Report", report_id)
    return report
