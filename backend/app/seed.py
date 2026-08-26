"""Seed emission_factors with plausible reference data.

Run:  docker compose exec backend python -m app.seed

Idempotent — skips any (source_type, region) pair that already exists.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.emission_factor import EmissionFactor

SEED_FACTORS = [
    {
        "source_type": "ENERGY",
        "region": "IN",
        "factor_value": Decimal("0.708200"),
        "unit": "kg_co2e_per_kwh",
        "valid_from": date(2026, 1, 1),
        "valid_to": None,
        "source_reference": (
            "CEA (Central Electricity Authority) CO2 Baseline Database "
            "for the Indian Power Sector, Version 19, December 2023 — "
            "weighted average grid emission factor for India"
        ),
    },
    {
        "source_type": "FUEL",
        "region": "IN",
        "factor_value": Decimal("2.683000"),
        "unit": "kg_co2e_per_litre",
        "valid_from": date(2026, 1, 1),
        "valid_to": None,
        "source_reference": (
            "IPCC 2006 Guidelines for National Greenhouse Gas Inventories, "
            "Volume 2, Chapter 3, Table 3.3.1 — diesel oil (gas/diesel oil) "
            "default emission factor"
        ),
    },
    {
        "source_type": "RESOURCE",
        "region": "IN",
        "factor_value": Decimal("0.910000"),
        "unit": "kg_co2e_per_kg",
        "valid_from": date(2026, 1, 1),
        "valid_to": None,
        "source_reference": (
            "GHG Protocol — Emission Factors for Cross Sector Tools, "
            "Scope 3: purchased goods — Portland cement, India average"
        ),
    },
]


def seed(db: Session) -> None:
    for factor_data in SEED_FACTORS:
        exists = (
            db.query(EmissionFactor)
            .filter(
                EmissionFactor.source_type == factor_data["source_type"],
                EmissionFactor.region == factor_data["region"],
            )
            .first()
        )
        if exists:
            print(
                f"  SKIP  {factor_data['source_type']}/{factor_data['region']} "
                f"— already exists (id={exists.id})"
            )
            continue

        row = EmissionFactor(**factor_data)
        db.add(row)
        db.flush()
        print(
            f"  ADD   {factor_data['source_type']}/{factor_data['region']} "
            f"— id={row.id}, factor={factor_data['factor_value']}"
        )

    db.commit()


if __name__ == "__main__":
    print("Seeding emission_factors …")
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
    print("Done.")
