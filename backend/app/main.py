"""Carbon Emissions Tracking Platform — FastAPI application entry point."""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth import get_current_user
from app.graphql.schema import graphql_router
from app.middleware.audit import AuditLogMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.ml import load_model
from app.pubsub import run_subscriber
from app.routers import (
    asset_scan,
    audit_logs,
    auth,
    consumption_records,
    emission_factors,
    emission_sources,
    facilities,
    organizations,
    reports,
    websocket,
)
from app.schemas.error import error_response


# ---------------------------------------------------------------------------
# Lifespan — the YOLOv8n model is loaded exactly once here, at process
# startup, before the app accepts traffic. Routes read the already-loaded
# instance via app.ml.get_yolo_model; nothing re-instantiates YOLO() per
# request. A cold-start delay during a live demo scan is unacceptable.
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.yolo_model = load_model()

    # Redis pub/sub subscriber bridging cross-process broadcasts (from the
    # Celery worker) onto this process's real WebSocket connections — see
    # app/pubsub.py. Skippable for the bulk of the test suite the same way
    # SKIP_MODEL_LOAD skips the YOLO model: most tests have nothing to do
    # with reports/WebSockets and shouldn't pay for a live Redis connection
    # on every TestClient startup, or hang if Redis isn't up yet.
    subscriber_task = None
    if os.getenv("SKIP_PUBSUB") != "true":
        subscriber_task = asyncio.create_task(run_subscriber())

    yield

    if subscriber_task is not None:
        subscriber_task.cancel()


app = FastAPI(
    title="Carbon Emissions Tracking Platform",
    description="Backend API for tracking organizational carbon emissions.",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — the frontend dev server runs on a different origin (Vite on
# localhost:5173) than the API (localhost:8000), so the browser enforces
# CORS on every request. Without this, all fetches fail at the preflight
# stage before the request ever reaches a route.
# ---------------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Audit logging — one audit_logs row per POST/PUT/PATCH/DELETE, written
# from a background task after the response is sent so no API call pays for
# it. See app/middleware/audit.py for the full rationale (why middleware
# rather than per-endpoint calls, and how it stays off the request path).
#
# add_middleware inserts at the front of the stack, so this ends up
# wrapping CORSMiddleware. Harmless: preflight OPTIONS requests, the only
# thing CORS answers on its own, are not an audited method.
# ---------------------------------------------------------------------------

app.add_middleware(AuditLogMiddleware)

# ---------------------------------------------------------------------------
# Security headers — HSTS plus companion hardening headers on every
# response, including error responses. Sent whether or not this process is
# the one terminating TLS: in production a platform terminates it upstream
# and this app sees plain HTTP, but the browser still needs to be told to
# stay on HTTPS. See app/middleware/security_headers.py.
# ---------------------------------------------------------------------------

app.add_middleware(SecurityHeadersMiddleware)

# ---------------------------------------------------------------------------
# Custom validation-error handler
# Transforms FastAPI's default 422 shape into the contract's standard error
# shape: {"error": {"code": "VALIDATION_ERROR", "message": "..."}}
# ---------------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    # Collect human-readable messages from each validation error
    messages = []
    for err in exc.errors():
        loc = " -> ".join(str(part) for part in err["loc"] if part != "body")
        msg = err["msg"]
        if loc:
            messages.append(f"{loc}: {msg}")
        else:
            messages.append(msg)
    combined = "; ".join(messages)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response("VALIDATION_ERROR", combined),
    )


# ---------------------------------------------------------------------------
# Custom HTTPException handler
# Auth dependencies (get_current_user) raise HTTPException with a
# {"code": ..., "message": ...} detail — reshape that (and any other
# HTTPException) into the contract's standard error shape.
# ---------------------------------------------------------------------------


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "code" in exc.detail and "message" in exc.detail:
        content = error_response(exc.detail["code"], exc.detail["message"])
    else:
        content = error_response("HTTP_ERROR", str(exc.detail))
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=exc.headers,
    )


# ---------------------------------------------------------------------------
# Router registration — all under /api prefix
# ---------------------------------------------------------------------------

app.include_router(auth.router, prefix="/api")
app.include_router(organizations.router, prefix="/api")
app.include_router(facilities.router, prefix="/api")
app.include_router(asset_scan.router, prefix="/api")
app.include_router(emission_sources.router, prefix="/api")
app.include_router(emission_factors.router, prefix="/api")
app.include_router(consumption_records.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(audit_logs.router, prefix="/api")
app.include_router(websocket.router)  # no /api prefix — matches /health

# GraphQL — read-only query layer alongside REST (REST stays the source of
# truth for all writes; there is no Mutation type). Also no /api prefix,
# same reasoning as /health and /ws. Gated by the exact same
# get_current_user dependency every REST router uses, applied here at
# include_router time since GraphQLRouter is a plain APIRouter — a request
# without a valid bearer token never reaches GraphQL execution at all.
app.include_router(
    graphql_router,
    prefix="/graphql",
    dependencies=[Depends(get_current_user)],
)


# ---------------------------------------------------------------------------
# Health check (no /api prefix — infrastructure probe)
# ---------------------------------------------------------------------------


@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness probe — returns OK when the service is running."""
    return {"status": "ok"}
