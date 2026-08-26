"""Standard error response shape used by all endpoints.

Contract: {"error": {"code": "...", "message": "..."}}
"""

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


def error_response(code: str, message: str) -> dict:
    """Build the standard error dict for JSONResponse."""
    return {"error": {"code": code, "message": message}}
