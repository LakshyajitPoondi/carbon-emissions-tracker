"""Carbon Emissions Tracking Platform — FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.ml import load_model
from app.routers import (
    asset_scan,
    auth,
    consumption_records,
    emission_factors,
    emission_sources,
    facilities,
    organizations,
    reports,
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
    yield


app = FastAPI(
    title="Carbon Emissions Tracking Platform",
    description="Backend API for tracking organizational carbon emissions.",
    version="0.1.0",
    lifespan=lifespan,
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
app.include_router(asset_scan.router, prefix="/api")
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
