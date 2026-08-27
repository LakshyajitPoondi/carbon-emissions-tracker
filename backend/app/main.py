"""Carbon Emissions Tracking Platform — FastAPI application entry point."""

import os

from fastapi import FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import (
    auth,
    consumption_records,
    emission_factors,
    emission_sources,
    facilities,
    organizations,
    reports,
)
from app.schemas.error import error_response

app = FastAPI(
    title="Carbon Emissions Tracking Platform",
    description="Backend API for tracking organizational carbon emissions.",
    version="0.1.0",
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
app.include_router(emission_sources.router, prefix="/api")
app.include_router(emission_factors.router, prefix="/api")
app.include_router(consumption_records.router, prefix="/api")
app.include_router(reports.router, prefix="/api")


# ---------------------------------------------------------------------------
# Health check (no /api prefix — infrastructure probe)
# ---------------------------------------------------------------------------


@app.get("/health", tags=["Health"])
async def health_check():
    """Liveness probe — returns OK when the service is running."""
    return {"status": "ok"}
