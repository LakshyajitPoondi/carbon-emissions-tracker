"""Carbon Emissions Tracking Platform — FastAPI application entry point."""

from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routers import (
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
# Router registration — all under /api prefix
# ---------------------------------------------------------------------------

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
