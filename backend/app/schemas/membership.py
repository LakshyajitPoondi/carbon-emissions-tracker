"""Request and response contracts for organization membership lifecycle."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

OrganizationRole = Literal["OWNER", "ADMIN", "EMPLOYEE"]
JoinRequestStatus = Literal["PENDING", "APPROVED", "REJECTED"]


class JoinCodeResponse(BaseModel):
    organization_id: int
    join_code: str


class JoinRequestCreate(BaseModel):
    join_code: str


class JoinRequestApproval(BaseModel):
    role: OrganizationRole


class JoinRequestResponse(BaseModel):
    id: int
    organization_id: int
    organization_name: str
    user_id: int
    user_email: str
    status: JoinRequestStatus
    requested_at: datetime
    decided_at: datetime | None
    decided_by: int | None


class MemberRoleUpdate(BaseModel):
    role: OrganizationRole


class OrganizationMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    email: str
    role: OrganizationRole
    joined_at: datetime

