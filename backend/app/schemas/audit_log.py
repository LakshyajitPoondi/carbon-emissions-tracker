"""Pydantic schemas for the AuditLog resource.

Matches docs/api-contract.md — Audit Logs section. Read-only: audit rows
are written by app/middleware/audit.py, never by a client, so there is no
Create schema here.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    """One entry in the GET /audit-logs response array."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int]
    action: str
    resource_type: str
    resource_id: Optional[int]
    endpoint: str
    status_code: int
    timestamp: datetime
