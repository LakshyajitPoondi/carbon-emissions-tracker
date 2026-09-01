"""Seed reference factors and, when explicitly enabled, an interactive demo.

Run:  docker compose exec backend python -m app.seed

The reference factors are always seeded. Demo accounts and organization data
are gated behind ``SEED_DEMO_ACCOUNTS=true`` and are disabled by default.
All operations are idempotent and never overwrite an existing user or row.
Disabling the flag later does not delete demo rows that were already created.
"""

import os
import secrets
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.auth import hash_password
from app.database import SessionLocal
from app.demo_data import (
    DEMO_FACILITIES,
    DEMO_INDUSTRY_TYPE,
    DEMO_ORGANIZATION_NAME,
    DEMO_PASSWORD,
    DEMO_PRODUCTS,
    DEMO_RECORDED_BY,
    DEMO_RECORD_TIMES,
    DEMO_SOURCES,
    DEMO_USERS,
)
from app.models.consumption_record import ConsumptionRecord
from app.models.emission_calculation import EmissionCalculation
from app.models.emission_factor import EmissionFactor
from app.models.emission_source import EmissionSource, SourceTypeEnum
from app.models.facility import Facility
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.product import Product
from app.models.report import Report, ReportStatusEnum
from app.models.user import User
from app.services.emissions import calculate_emissions, find_applicable_emission_factor
from app.services.barcodes import render_ean13_png
from app.services.memberships import generate_unique_join_code
from app.services.reports import organization_report_totals

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


def _demo_seed_enabled() -> bool:
    return os.getenv("SEED_DEMO_ACCOUNTS", "false").strip().lower() == "true"


def seed_factors(db: Session) -> None:
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

    db.flush()


def seed_demo_data(
    db: Session, *, organization_name: str = DEMO_ORGANIZATION_NAME
) -> Organization:
    """Create the opt-in demo fixture without replacing existing values."""
    organization = (
        db.query(Organization)
        .filter(
            Organization.name == organization_name,
            Organization.industry_type == DEMO_INDUSTRY_TYPE,
        )
        .first()
    )
    if organization is None:
        organization = Organization(
            name=organization_name,
            industry_type=DEMO_INDUSTRY_TYPE,
            join_code=generate_unique_join_code(db),
        )
        db.add(organization)
        db.flush()
        print(f"  ADD   demo organization — id={organization.id}")
    else:
        print(f"  SKIP  demo organization — already exists (id={organization.id})")

    for fixture in DEMO_USERS:
        user = db.query(User).filter(User.email == fixture["email"]).first()
        if user is None:
            password = DEMO_PASSWORD if fixture["can_sign_in"] else secrets.token_urlsafe(48)
            user = User(email=fixture["email"], hashed_password=hash_password(password))
            db.add(user)
            db.flush()
            print(f"  ADD   demo user {fixture['email']}")
        else:
            print(f"  SKIP  demo user {fixture['email']} — already exists")
        membership = (
            db.query(OrganizationMember)
            .filter(
                OrganizationMember.user_id == user.id,
                OrganizationMember.organization_id == organization.id,
            )
            .first()
        )
        if membership is None:
            db.add(
                OrganizationMember(
                    user_id=user.id,
                    organization_id=organization.id,
                    role=fixture["role"],
                )
            )
            print(f"  ADD   {fixture['role']} membership for {fixture['email']}")

    facilities_by_name: dict[str, Facility] = {}
    for fixture in DEMO_FACILITIES:
        facility = (
            db.query(Facility)
            .filter(
                Facility.organization_id == organization.id,
                Facility.name == fixture["name"],
            )
            .first()
        )
        if facility is None:
            facility = Facility(
                organization_id=organization.id,
                name=fixture["name"],
                location=fixture["location"],
                facility_type=fixture["facility_type"],
            )
            db.add(facility)
            db.flush()
            print(f"  ADD   facility {fixture['name']}")
        facilities_by_name[fixture["name"]] = facility

    for fixture in DEMO_SOURCES:
        facility = facilities_by_name[fixture["facility"]]
        source = (
            db.query(EmissionSource)
            .filter(
                EmissionSource.facility_id == facility.id,
                EmissionSource.source_name == fixture["source_name"],
            )
            .first()
        )
        if source is None:
            source = EmissionSource(
                facility_id=facility.id,
                source_type=SourceTypeEnum(fixture["source_type"]),
                source_name=fixture["source_name"],
                unit_of_measurement=fixture["unit"],
                barcode_value=fixture["barcode"],
            )
            db.add(source)
            db.flush()
            print(f"  ADD   source {facility.name} / {source.source_name}")

        for recorded_at, quantity in zip(DEMO_RECORD_TIMES, fixture["quantities"]):
            record = (
                db.query(ConsumptionRecord)
                .filter(
                    ConsumptionRecord.emission_source_id == source.id,
                    ConsumptionRecord.recorded_at == recorded_at,
                )
                .first()
            )
            if record is None:
                record = ConsumptionRecord(
                    emission_source_id=source.id,
                    facility_id=facility.id,
                    quantity_consumed=quantity,
                    unit=fixture["unit"],
                    recorded_at=recorded_at,
                    recorded_by=DEMO_RECORDED_BY,
                )
                db.add(record)
                db.flush()

            calculation = (
                db.query(EmissionCalculation)
                .filter(EmissionCalculation.consumption_record_id == record.id)
                .first()
            )
            if calculation is None:
                factor = find_applicable_emission_factor(
                    db, SourceTypeEnum(fixture["source_type"]), recorded_at.date()
                )
                if factor is None:
                    raise RuntimeError(
                        f"No emission factor for {fixture['source_type']} on "
                        f"{recorded_at.date()}"
                    )
                db.add(
                    EmissionCalculation(
                        consumption_record_id=record.id,
                        emission_factor_id=factor.id,
                        calculated_emissions_kg_co2e=calculate_emissions(
                            quantity, factor.factor_value
                        ),
                        calculation_date=recorded_at.date(),
                    )
                )

    for fixture in DEMO_PRODUCTS:
        exists = (
            db.query(Product)
            .filter(
                Product.organization_id == organization.id,
                Product.barcode == fixture["barcode"],
            )
            .first()
        )
        if exists is None:
            db.add(
                Product(
                    organization_id=organization.id,
                    barcode_image=render_ean13_png(fixture["barcode"]),
                    **fixture,
                )
            )
            print(f"  ADD   product {fixture['name']} ({fixture['barcode']})")
        elif exists.barcode_image is None:
            # The barcode-image column was introduced after the original
            # demo fixture. Fill only that new missing value; never replace
            # an existing Product field or image.
            exists.barcode_image = render_ean13_png(fixture["barcode"])
            print(f"  ADD   barcode image for {fixture['name']}")

    db.flush()
    report_start = date(2026, 8, 1)
    report_end = date(2026, 8, 31)
    report = (
        db.query(Report)
        .filter(
            Report.organization_id == organization.id,
            Report.report_period_start == report_start,
            Report.report_period_end == report_end,
        )
        .first()
    )
    if report is None:
        total, breakdown = organization_report_totals(
            db, organization.id, report_start, report_end
        )
        serializable_breakdown = [
            {**row, "total_emissions_kg_co2e": str(row["total_emissions_kg_co2e"])}
            for row in breakdown
        ]
        db.add(
            Report(
                organization_id=organization.id,
                report_period_start=report_start,
                report_period_end=report_end,
                status=ReportStatusEnum.FINAL,
                total_emissions_kg_co2e=total,
                facilities_breakdown=serializable_breakdown,
            )
        )
        print(f"  ADD   August 2026 demo report — {total} kg CO2e")

    return organization


def seed(db: Session, *, include_demo: bool | None = None) -> None:
    seed_factors(db)
    should_seed_demo = _demo_seed_enabled() if include_demo is None else include_demo
    if should_seed_demo:
        print("Seeding opt-in demo accounts and organization data …")
        seed_demo_data(db)
    else:
        print("  SKIP  demo accounts — set SEED_DEMO_ACCOUNTS=true to enable")
    db.commit()


if __name__ == "__main__":
    print("Seeding reference data …")
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
    print("Done.")
