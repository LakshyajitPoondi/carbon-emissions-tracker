"""Pydantic schemas for the Asset Scan resource.

Matches docs/api-contract.md — Asset Scan section. No confidence field on
success: pyzbar's decode is a deterministic pass/fail, not a probabilistic
score (see docs/asset-scan-plan.md, Decision B).
"""

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from app.schemas.emission_source import EmissionSourceResponse
from app.schemas.product import ProductResponse


class AssetScanEmissionSourceResponse(BaseModel):
    match_type: Literal["emission_source"]
    data: EmissionSourceResponse


class AssetScanProductResponse(BaseModel):
    match_type: Literal["product"]
    data: ProductResponse


AssetScanResponse = Annotated[
    Union[AssetScanEmissionSourceResponse, AssetScanProductResponse],
    Field(discriminator="match_type"),
]
