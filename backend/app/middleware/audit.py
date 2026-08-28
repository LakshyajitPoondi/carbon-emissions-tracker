"""Audit-logging middleware.

Records one `audit_logs` row per mutating request (POST/PUT/PATCH/DELETE),
capturing who did it, what kind of resource it touched, the endpoint, and
the status code the request ended with.

Why middleware rather than per-endpoint calls
---------------------------------------------
Auditing wired into each handler covers exactly the handlers someone
remembered to wire it into, and silently stops covering the next endpoint
added. One middleware sees every request that reaches the app, including
requests that fail — 401s, 404s, and validation 422s are logged with their
real status code, which is the half of an audit trail that actually matters
for "who tried what".

Why it doesn't slow the request down (requirement 3)
----------------------------------------------------
The work done on the request path is string parsing of the URL — no I/O.
The database write is handed to a Starlette ``BackgroundTask`` attached to
the response, which Starlette runs *after* the response body has been sent
to the client, so the client's latency is unchanged. Because
``_write_audit_log`` is a plain ``def``, Starlette runs it in a threadpool
rather than on the event loop, so the synchronous SQLAlchemy write never
blocks other requests either.

And it can't break the request: the write is wrapped so that no exception
escapes ``_write_audit_log``. Even if one did, it runs after the response is
already on the wire, so the client still has its result. A database that
refuses audit writes degrades auditing, never the API.

The one exception is the unhandled-500 path. An exception from
``call_next`` never becomes a response at this layer (Starlette's
``ServerErrorMiddleware`` sits outside all user middleware), so there is no
response to hang a background task on; that row is written inline via
``run_in_threadpool`` before the exception is re-raised. Adding a few
milliseconds to a request that already crashed is a fine trade for not
having crashes be the one thing missing from the audit trail.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from starlette.background import BackgroundTask, BackgroundTasks
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.database import SessionLocal
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

API_PREFIX = "/api"

# Reads are not audited — only state changes are.
AUDITED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

ACTION_BY_METHOD = {
    "POST": "CREATE",
    "PUT": "UPDATE",
    "PATCH": "UPDATE",
    "DELETE": "DELETE",
}

# Registering and logging in are POSTs, but they aren't data mutations of
# the kind this trail exists to record, and POST /auth/token in particular
# is hit on every login. Excluded by exact path.
EXCLUDED_PATHS = frozenset({"/api/auth/register", "/api/auth/token"})

# Keep in step with AuditLog.endpoint / .resource_type column widths.
MAX_ENDPOINT_LENGTH = 255
MAX_RESOURCE_TYPE_LENGTH = 64

UNKNOWN_RESOURCE_TYPE = "unknown"


def _singularize(word: str) -> str:
    """Collection segment -> singular resource name. Deliberately a small
    set of rules, not an inflection library: every collection this API
    exposes is a regular plural ("facilities", "emission-sources")."""
    if word.endswith("ies") and len(word) > 3:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def derive_resource(path: str) -> tuple[str, Optional[int]]:
    """Derive ``(resource_type, resource_id)`` from a URL path.

    Numeric segments are ids; everything else names something. Which
    non-numeric segment is *the* resource depends on what precedes it:

    - ``/api/organizations``            -> ("organization", None)
    - ``/api/facilities/5``             -> ("facility", 5)
    - ``/api/facilities/1/asset-scan``  -> ("asset_scan", 1)
    - ``/api/reports/generate``         -> ("report", None)

    The last two are the interesting pair. A non-numeric segment sitting
    directly after an id is a sub-resource of it, so it wins ("asset_scan").
    A non-numeric segment sitting directly after another non-numeric one is
    an action verb on that collection, not a resource, so the collection
    wins ("report", not "generate").

    ``resource_id`` is the last id in the path, which for a nested route is
    the parent's id (the facility in ``/facilities/1/asset-scan``) — the
    only id knowable from the request itself.
    """
    trimmed = path[len(API_PREFIX):] if path.startswith(API_PREFIX + "/") else path
    segments = [segment for segment in trimmed.split("/") if segment]

    resource_id: Optional[int] = None
    for segment in segments:
        if segment.isdigit():
            resource_id = int(segment)

    named = [(index, seg) for index, seg in enumerate(segments) if not seg.isdigit()]
    if not named:
        return UNKNOWN_RESOURCE_TYPE, resource_id

    index, candidate = named[-1]
    if index > 0 and not segments[index - 1].isdigit():
        # Trailing action verb ("generate") — the resource is what it acts on.
        candidate = segments[index - 1]

    resource_type = _singularize(candidate).replace("-", "_")
    return resource_type[:MAX_RESOURCE_TYPE_LENGTH], resource_id


def _write_audit_log(
    *,
    user_id: Optional[int],
    action: str,
    resource_type: str,
    resource_id: Optional[int],
    endpoint: str,
    status_code: int,
) -> None:
    """Insert one audit row. Never raises — see the module docstring.

    Uses its own session rather than the request's: the request's session is
    already closed by the time this runs (the response has been sent), and
    an audit row must not be rolled back along with a failed request's
    transaction. ``SessionLocal`` is read from the module globals at call
    time so tests can rebind it to their own connection (see conftest.py).
    """
    session = None
    try:
        session = SessionLocal()
        session.add(
            AuditLog(
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                endpoint=endpoint,
                status_code=status_code,
                timestamp=datetime.now(timezone.utc),
            )
        )
        session.commit()
    except Exception:  # noqa: BLE001 — auditing must never break the API
        logger.exception("Failed to write audit log for %s %s", action, endpoint)
        if session is not None:
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                logger.exception("Failed to roll back the audit-log session")
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:  # noqa: BLE001
                logger.exception("Failed to close the audit-log session")


def _authenticated_user_id(request: Request) -> Optional[int]:
    """The user id stashed on request.state by app.auth.get_current_user.

    Read after the route has run, so it reflects a JWT that the existing
    auth dependency already validated — the middleware never decodes or
    trusts a token itself. Absent (None) when auth never succeeded, which
    is precisely the case a rejected request should record.
    """
    return getattr(request.state, "audit_user_id", None)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Attaches an audit-log write to every mutating request's response."""

    async def dispatch(self, request: Request, call_next):
        method = request.method.upper()
        path = request.url.path

        if method not in AUDITED_METHODS or path in EXCLUDED_PATHS:
            return await call_next(request)

        resource_type, resource_id = derive_resource(path)
        fields = {
            "action": ACTION_BY_METHOD[method],
            "resource_type": resource_type,
            "resource_id": resource_id,
            "endpoint": path[:MAX_ENDPOINT_LENGTH],
        }

        try:
            response = await call_next(request)
        except Exception:
            # Unhandled 500: no response object exists here to defer the
            # write onto, so write it inline (off the event loop) and let
            # the exception continue to ServerErrorMiddleware untouched.
            await run_in_threadpool(
                _write_audit_log,
                user_id=_authenticated_user_id(request),
                status_code=500,
                **fields,
            )
            raise

        task = BackgroundTask(
            _write_audit_log,
            user_id=_authenticated_user_id(request),
            status_code=response.status_code,
            **fields,
        )

        # Nothing in the app attaches background tasks today, but appending
        # rather than overwriting means auditing never silently eats one.
        existing = getattr(response, "background", None)
        response.background = task if existing is None else BackgroundTasks([existing, task])
        return response
