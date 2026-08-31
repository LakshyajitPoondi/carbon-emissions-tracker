"""WebSocket endpoints for live dashboard/report updates.

GET /ws/facilities/{facility_id} — a client connects once per facility it's
viewing, and receives a message whenever a new consumption record is created
for that facility (see consumption_records.py's broadcast call).

GET /ws/organizations/{organization_id} — a client connects once per
organization it's viewing reports for, and receives a message when an async
report generation task finishes (see app/tasks.py, via the Redis bridge in
app/pubsub.py — the Celery worker that finishes the report runs in a
different process than this one).

Both registered without the /api prefix, matching the existing /health
endpoint's pattern of sitting outside the versioned REST namespace.

Auth uses the same JWT as every other endpoint, but passed as a query param
(?token=...) rather than an Authorization header — browser WebSocket
handshakes can't carry custom headers the way HTTP requests can.
"""

from typing import Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.auth import get_user_from_token
from app.authorization import OrganizationAction, has_organization_access
from app.database import get_db
from app.models.facility import Facility
from app.models.organization import Organization
from app.ws import manager

router = APIRouter(prefix="/ws", tags=["WebSocket"])

# RFC 6455's standard code for "you violated my policy" — the closest fit
# for missing/invalid auth; there's no more specific standard code for it.
CLOSE_UNAUTHORIZED = 1008
# Private-use range (4000-4999, reserved by RFC 6455 for applications) —
# mirrors HTTP 404 for "the resource you asked for doesn't exist."
CLOSE_NOT_FOUND = 4004


async def _run_channel(websocket: WebSocket, channel: str) -> None:
    """Shared accept/listen/cleanup loop for any channel, once auth and the
    resource lookup have already passed."""
    await websocket.accept()
    manager.connect(channel, websocket)
    try:
        while True:
            # Clients aren't expected to send anything meaningful — this
            # just blocks until the client disconnects, which is how ASGI
            # WebSocket disconnect detection works (a receive() that raises
            # WebSocketDisconnect).
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(channel, websocket)


@router.websocket("/facilities/{facility_id}")
async def facility_updates(
    websocket: WebSocket,
    facility_id: int,
    token: Optional[str] = None,
    db: Session = Depends(get_db),
):
    user = get_user_from_token(token, db) if token else None
    if user is None:
        # Reject before accept() — never silently accept an unauthenticated
        # connection.
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return

    facility = db.get(Facility, facility_id)
    # Membership is checked before accept(), so a non-member is never added
    # to the broadcast channel — not accepted-then-dropped, never joined.
    #
    # Deliberately the same close code as "no such facility": a distinct
    # forbidden code would let anyone enumerate valid facility ids over the
    # socket, undoing the 404 masking the REST layer does.
    if facility is None or not has_organization_access(
        db,
        user.id,
        facility.organization_id,
        OrganizationAction.VIEW,
    ):
        await websocket.close(code=CLOSE_NOT_FOUND)
        return

    await _run_channel(websocket, f"facility:{facility_id}")


@router.websocket("/organizations/{organization_id}")
async def organization_updates(
    websocket: WebSocket,
    organization_id: int,
    token: Optional[str] = None,
    db: Session = Depends(get_db),
):
    user = get_user_from_token(token, db) if token else None
    if user is None:
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return

    organization = db.get(Organization, organization_id)
    # Same masking as the facility channel above.
    if organization is None or not has_organization_access(
        db, user.id, organization_id, OrganizationAction.VIEW
    ):
        await websocket.close(code=CLOSE_NOT_FOUND)
        return

    await _run_channel(websocket, f"organization:{organization_id}")
