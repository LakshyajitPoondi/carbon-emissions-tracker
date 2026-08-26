"""Emission Factor endpoints.

GET /emission-factors?source_type={type}&region={region} — list emission factors

Read-only: emission_factors is seeded via app/seed.py, not created through the API.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.emission_factor import EmissionFactor
from app.schemas.emission_factor import EmissionFactorResponse

router = APIRouter(prefix="/emission-factors", tags=["Emission Factors"])


@router.get(
    "",
    response_model=list[EmissionFactorResponse],
)
def list_emission_factors(
    source_type: Optional[str] = Query(None, description="Filter by source type"),
    region: Optional[str] = Query(None, description="Filter by region"),
    db: Session = Depends(get_db),
):
    query = db.query(EmissionFactor)
    if source_type is not None:
        query = query.filter(EmissionFactor.source_type == source_type)
    if region is not None:
        query = query.filter(EmissionFactor.region == region)
    return query.order_by(EmissionFactor.id).all()
