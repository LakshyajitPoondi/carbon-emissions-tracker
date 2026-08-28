"""Audit log endpoints.

GET /audit-logs?resource_type=&user_id=&limit=&offset=
    — read back the trail written by app/middleware/audit.py, most recent
      first. Read-only by design: nothing may create, edit, or delete an
      audit entry through the API, which is the whole point of one.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models.audit_log import AuditLog
from app.schemas.audit_log import AuditLogResponse

router = APIRouter(
    prefix="/audit-logs",
    tags=["Audit Logs"],
    dependencies=[Depends(get_current_user)],
)

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


@router.get("", response_model=list[AuditLogResponse])
def list_audit_logs(
    resource_type: Optional[str] = Query(
        None, description='Filter by resource type, e.g. "organization"'
    ),
    user_id: Optional[int] = Query(None, description="Filter by acting user ID"),
    limit: int = Query(
        DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Max entries to return"
    ),
    offset: int = Query(0, ge=0, description="Entries to skip, for paging"),
    db: Session = Depends(get_db),
):
    query = db.query(AuditLog)
    if resource_type is not None:
        query = query.filter(AuditLog.resource_type == resource_type)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)

    # id desc breaks ties: rows written within the same clock tick would
    # otherwise page nondeterministically, which is how offset pagination
    # ends up silently skipping or repeating entries.
    return (
        query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
