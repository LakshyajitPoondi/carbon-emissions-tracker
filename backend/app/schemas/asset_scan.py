"""Pydantic schemas for the Asset Scan resource.

Matches docs/api-contract.md — Asset Scan section. No confidence field on
success: pyzbar's decode is a deterministic pass/fail, not a probabilistic
score (see docs/asset-scan-plan.md, Decision B).
"""

from pydantic import BaseModel

from app.schemas.emission_source import EmissionSourceResponse


class BoundingBoxResponse(BaseModel):
    x: int
    y: int
    width: int
    height: int


class AssetScanResponse(BaseModel):
    decoded_value: str
    bounding_box: BoundingBoxResponse
    emission_source: EmissionSourceResponse
