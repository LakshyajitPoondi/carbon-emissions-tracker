"""Join-request and organization member-management endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.authorization import OrganizationAction, require_organization
from app.auth import get_current_user
from app.database import get_db
from app.models.organization import Organization
from app.models.organization_join_request import (
    JOIN_STATUS_APPROVED,
    JOIN_STATUS_PENDING,
    JOIN_STATUS_REJECTED,
    OrganizationJoinRequest,
)
from app.models.organization_member import ROLE_OWNER, OrganizationMember
from app.models.user import User
from app.schemas.membership import (
    JoinCodeResponse,
    JoinRequestApproval,
    JoinRequestCreate,
    JoinRequestResponse,
    MemberRoleUpdate,
    OrganizationMemberResponse,
)
from app.services.memberships import generate_unique_join_code, normalize_join_code

router = APIRouter(
    tags=["Organization membership"],
    dependencies=[Depends(get_current_user)],
)


def _not_found(resource: str, identifier: int | None = None) -> HTTPException:
    suffix = f" {identifier}" if identifier is not None else ""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "NOT_FOUND",
            "message": f"{resource}{suffix} does not exist",
        },
    )


def _unprocessable(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": code, "message": message},
    )


def _join_request_response(request: OrganizationJoinRequest) -> JoinRequestResponse:
    return JoinRequestResponse(
        id=request.id,
        organization_id=request.organization_id,
        organization_name=request.organization.name,
        user_id=request.user_id,
        user_email=request.user.email,
        status=request.status,
        requested_at=request.requested_at,
        decided_at=request.decided_at,
        decided_by=request.decided_by,
    )


def _member_response(member: OrganizationMember, email: str) -> OrganizationMemberResponse:
    return OrganizationMemberResponse(
        user_id=member.user_id,
        email=email,
        role=member.role,
        joined_at=member.created_at,
    )


@router.get(
    "/organizations/{organization_id}/join-code",
    response_model=JoinCodeResponse,
)
def get_join_code(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    organization = require_organization(
        db, current_user, organization_id, OrganizationAction.WRITE
    )
    return JoinCodeResponse(
        organization_id=organization.id, join_code=organization.join_code
    )


@router.post(
    "/organizations/{organization_id}/join-code/regenerate",
    response_model=JoinCodeResponse,
)
def regenerate_join_code(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    organization = require_organization(
        db, current_user, organization_id, OrganizationAction.WRITE
    )
    organization.join_code = generate_unique_join_code(db)
    db.commit()
    db.refresh(organization)
    return JoinCodeResponse(
        organization_id=organization.id, join_code=organization.join_code
    )


@router.post(
    "/join-requests",
    response_model=JoinRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_join_request(
    body: JoinRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    join_code = normalize_join_code(body.join_code)
    organization = (
        db.query(Organization).filter(Organization.join_code == join_code).first()
    )
    if organization is None:
        # Deliberately identical for an empty, malformed, or unknown code.
        raise _not_found("Organization join code")

    existing_member = (
        db.query(OrganizationMember.id)
        .filter(
            OrganizationMember.user_id == current_user.id,
            OrganizationMember.organization_id == organization.id,
        )
        .first()
    )
    if existing_member is not None:
        raise _unprocessable(
            "ALREADY_ORGANIZATION_MEMBER",
            "You are already a member of this organization",
        )

    pending = (
        db.query(OrganizationJoinRequest.id)
        .filter(
            OrganizationJoinRequest.user_id == current_user.id,
            OrganizationJoinRequest.organization_id == organization.id,
            OrganizationJoinRequest.status == JOIN_STATUS_PENDING,
        )
        .first()
    )
    if pending is not None:
        raise _unprocessable(
            "JOIN_REQUEST_ALREADY_PENDING",
            "A join request for this organization is already pending",
        )

    request = OrganizationJoinRequest(
        user_id=current_user.id,
        organization_id=organization.id,
        status=JOIN_STATUS_PENDING,
    )
    db.add(request)
    try:
        db.commit()
    except IntegrityError:
        # The partial unique index is the final guard if two submissions race.
        db.rollback()
        raise _unprocessable(
            "JOIN_REQUEST_ALREADY_PENDING",
            "A join request for this organization is already pending",
        )
    db.refresh(request)
    return _join_request_response(request)


@router.get("/join-requests/me", response_model=list[JoinRequestResponse])
def list_my_pending_join_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    requests = (
        db.query(OrganizationJoinRequest)
        .filter(
            OrganizationJoinRequest.user_id == current_user.id,
            OrganizationJoinRequest.status == JOIN_STATUS_PENDING,
        )
        .order_by(
            OrganizationJoinRequest.requested_at.desc(),
            OrganizationJoinRequest.id.desc(),
        )
        .all()
    )
    return [_join_request_response(request) for request in requests]


@router.get(
    "/organizations/{organization_id}/join-requests",
    response_model=list[JoinRequestResponse],
)
def list_pending_join_requests(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_organization(db, current_user, organization_id, OrganizationAction.WRITE)
    requests = (
        db.query(OrganizationJoinRequest)
        .filter(
            OrganizationJoinRequest.organization_id == organization_id,
            OrganizationJoinRequest.status == JOIN_STATUS_PENDING,
        )
        .order_by(
            OrganizationJoinRequest.requested_at.asc(),
            OrganizationJoinRequest.id.asc(),
        )
        .all()
    )
    return [_join_request_response(request) for request in requests]


def _pending_request_for_decision(
    db: Session, organization_id: int, request_id: int
) -> OrganizationJoinRequest:
    request = (
        db.query(OrganizationJoinRequest)
        .filter(
            OrganizationJoinRequest.id == request_id,
            OrganizationJoinRequest.organization_id == organization_id,
        )
        .with_for_update()
        .first()
    )
    if request is None:
        raise _not_found("Join request", request_id)
    if request.status != JOIN_STATUS_PENDING:
        raise _unprocessable(
            "JOIN_REQUEST_ALREADY_DECIDED",
            "This join request has already been decided",
        )
    return request


@router.post(
    "/organizations/{organization_id}/join-requests/{request_id}/approve",
    response_model=JoinRequestResponse,
)
def approve_join_request(
    organization_id: int,
    request_id: int,
    body: JoinRequestApproval,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_organization(db, current_user, organization_id, OrganizationAction.WRITE)
    request = _pending_request_for_decision(db, organization_id, request_id)

    existing_member = (
        db.query(OrganizationMember.id)
        .filter(
            OrganizationMember.user_id == request.user_id,
            OrganizationMember.organization_id == organization_id,
        )
        .first()
    )
    if existing_member is not None:
        raise _unprocessable(
            "ALREADY_ORGANIZATION_MEMBER",
            "The requester is already a member of this organization",
        )

    db.add(
        OrganizationMember(
            user_id=request.user_id,
            organization_id=organization_id,
            role=body.role,
        )
    )
    request.status = JOIN_STATUS_APPROVED
    request.decided_at = datetime.now(timezone.utc)
    request.decided_by = current_user.id
    db.commit()
    db.refresh(request)
    return _join_request_response(request)


@router.post(
    "/organizations/{organization_id}/join-requests/{request_id}/reject",
    response_model=JoinRequestResponse,
)
def reject_join_request(
    organization_id: int,
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_organization(db, current_user, organization_id, OrganizationAction.WRITE)
    request = _pending_request_for_decision(db, organization_id, request_id)
    request.status = JOIN_STATUS_REJECTED
    request.decided_at = datetime.now(timezone.utc)
    request.decided_by = current_user.id
    db.commit()
    db.refresh(request)
    return _join_request_response(request)


@router.get(
    "/organizations/{organization_id}/members",
    response_model=list[OrganizationMemberResponse],
)
def list_members(
    organization_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_organization(db, current_user, organization_id, OrganizationAction.VIEW)
    rows = (
        db.query(OrganizationMember, User.email)
        .join(User, User.id == OrganizationMember.user_id)
        .filter(OrganizationMember.organization_id == organization_id)
        .order_by(User.email.asc(), OrganizationMember.user_id.asc())
        .all()
    )
    return [_member_response(member, email) for member, email in rows]


def _locked_organization_members(
    db: Session, organization_id: int
) -> list[OrganizationMember]:
    # Lock the complete, deterministically ordered membership set so two
    # concurrent owner demotions/removals cannot both observe another owner.
    return (
        db.query(OrganizationMember)
        .filter(OrganizationMember.organization_id == organization_id)
        .order_by(OrganizationMember.id.asc())
        .with_for_update()
        .all()
    )


def _target_member(
    members: list[OrganizationMember], user_id: int
) -> OrganizationMember:
    member = next((item for item in members if item.user_id == user_id), None)
    if member is None:
        raise _not_found("Organization member", user_id)
    return member


def _protect_last_owner(
    members: list[OrganizationMember], target: OrganizationMember
) -> None:
    if target.role != ROLE_OWNER:
        return
    owner_count = sum(member.role == ROLE_OWNER for member in members)
    if owner_count <= 1:
        raise _unprocessable(
            "LAST_OWNER_REQUIRED",
            "An organization must have at least one OWNER",
        )


@router.patch(
    "/organizations/{organization_id}/members/{user_id}",
    response_model=OrganizationMemberResponse,
)
def update_member_role(
    organization_id: int,
    user_id: int,
    body: MemberRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_organization(db, current_user, organization_id, OrganizationAction.WRITE)
    members = _locked_organization_members(db, organization_id)
    target = _target_member(members, user_id)
    if target.role == ROLE_OWNER and body.role != ROLE_OWNER:
        _protect_last_owner(members, target)
    target.role = body.role
    email = target.user.email
    db.commit()
    db.refresh(target)
    return _member_response(target, email)


@router.delete(
    "/organizations/{organization_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_member(
    organization_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_organization(db, current_user, organization_id, OrganizationAction.WRITE)
    members = _locked_organization_members(db, organization_id)
    target = _target_member(members, user_id)
    _protect_last_owner(members, target)
    db.delete(target)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

