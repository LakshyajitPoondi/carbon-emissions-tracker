"""Emissions calculation and emission-factor lookup.

Keeps the actual arithmetic (and the factor-selection rule) out of the
consumption-records router, per agents/core.md.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.emission_factor import EmissionFactor
from app.models.emission_source import SourceTypeEnum

# MVP assumption: neither Organization nor Facility carries a region/country
# field, and the only emission factors seeded so far are region="IN". Until
# the platform needs to support more than one region, factor lookup is
# hardcoded to "IN" rather than threading a region through every request.
DEFAULT_REGION = "IN"

# Matches emission_calculations.calculated_emissions_kg_co2e — Numeric(14, 4).
CALCULATION_QUANT = Decimal("0.0001")


def find_applicable_emission_factor(
    db: Session,
    source_type: SourceTypeEnum,
    as_of: date,
    region: str = DEFAULT_REGION,
) -> Optional[EmissionFactor]:
    """Return the emission factor covering *source_type*/*region* on *as_of*.

    If more than one factor's validity window covers the date, the most
    recently published one (highest valid_from) wins.
    """
    return (
        db.query(EmissionFactor)
        .filter(
            EmissionFactor.source_type == source_type.value,
            EmissionFactor.region == region,
            EmissionFactor.valid_from <= as_of,
            or_(EmissionFactor.valid_to.is_(None), EmissionFactor.valid_to >= as_of),
        )
        .order_by(EmissionFactor.valid_from.desc())
        .first()
    )


def calculate_emissions(quantity_consumed: Decimal, factor_value: Decimal) -> Decimal:
    """Compute kg CO2e for a consumed quantity against an emission factor."""
    return (quantity_consumed * factor_value).quantize(
        CALCULATION_QUANT, rounding=ROUND_HALF_UP
    )
