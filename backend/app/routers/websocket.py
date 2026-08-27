"""WebSocket endpoint for live dashboard updates.

GET /ws/facilities/{facility_id} — a client connects once per facility it's
viewing, and receives a message whenever a new consumption record is created
for that facility (see consumption_records.py's broadcast call). Registered
without the /api prefix, matching the existing /health endpoint's pattern of
sitting outside the versioned REST namespace.

Auth uses the same JWT as every other endpoint, but passed as a query param
(?token=...) rather than an Authorization header — browser WebSocket
handshakes can't carry custom headers the way HTTP requests can.
"""

from typing import Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.auth import get_user_from_token
from app.database import get_db
from app.models.facility import Facility
from app.ws import manager

router = APIRouter(prefix="/ws", tags=["WebSocket"])

# RFC 6455's standard code for "you violated my policy" — the closest fit
# for missing/invalid auth; there's no more specific standard code for it.
CLOSE_UNAUTHORIZED = 1008
# Private-use range (4000-4999, reserved by RFC 6455 for applications) —
# mirrors HTTP 404 for "the facility you asked for doesn't exist."
CLOSE_FACILITY_NOT_FOUND = 4004


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
    if facility is None:
        await websocket.close(code=CLOSE_FACILITY_NOT_FOUND)
        return

    await websocket.accept()
    manager.connect(facility_id, websocket)
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
        manager.disconnect(facility_id, websocket)
