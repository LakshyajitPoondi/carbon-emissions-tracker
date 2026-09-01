"""Opt-in demo seeding is gated, complete, and repeatable."""

from app.demo_data import DEMO_PRODUCTS, DEMO_USERS
from app.models.consumption_record import ConsumptionRecord
from app.models.emission_calculation import EmissionCalculation
from app.models.emission_source import EmissionSource
from app.models.facility import Facility
from app.models.organization_member import OrganizationMember
from app.models.product import Product
from app.models.report import Report
from app.seed import _demo_seed_enabled, seed_demo_data, seed_factors
from app.services.barcodes import ean13_from_sequence


def _counts(db_session, organization_id: int) -> tuple[int, ...]:
    facilities = db_session.query(Facility).filter_by(organization_id=organization_id)
    facility_ids = [facility.id for facility in facilities]
    sources = db_session.query(EmissionSource).filter(
        EmissionSource.facility_id.in_(facility_ids)
    )
    source_ids = [source.id for source in sources]
    records = db_session.query(ConsumptionRecord).filter(
        ConsumptionRecord.emission_source_id.in_(source_ids)
    )
    record_ids = [record.id for record in records]
    return (
        db_session.query(OrganizationMember).filter_by(organization_id=organization_id).count(),
        len(facility_ids),
        len(source_ids),
        len(record_ids),
        db_session.query(EmissionCalculation)
        .filter(EmissionCalculation.consumption_record_id.in_(record_ids))
        .count(),
        db_session.query(Product).filter_by(organization_id=organization_id).count(),
        db_session.query(Report).filter_by(organization_id=organization_id).count(),
    )


def test_demo_seed_gate_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SEED_DEMO_ACCOUNTS", raising=False)
    assert _demo_seed_enabled() is False

    monkeypatch.setenv("SEED_DEMO_ACCOUNTS", "true")
    assert _demo_seed_enabled() is True


def test_demo_seed_is_complete_and_idempotent(db_session):
    seed_factors(db_session)
    organization = seed_demo_data(
        db_session, organization_name="Demo Organization (seed test)"
    )
    db_session.flush()

    expected = (len(DEMO_USERS), 3, 8, 24, 24, len(DEMO_PRODUCTS), 1)
    assert _counts(db_session, organization.id) == expected
    assert all(
        product.barcode_image is not None
        for product in db_session.query(Product)
        .filter_by(organization_id=organization.id)
        .all()
    )

    same_organization = seed_demo_data(
        db_session, organization_name="Demo Organization (seed test)"
    )
    db_session.flush()
    assert same_organization.id == organization.id
    assert _counts(db_session, organization.id) == expected


def test_demo_product_barcodes_are_valid_stable_ean13_values():
    assert [product["barcode"] for product in DEMO_PRODUCTS] == [
        ean13_from_sequence(index) for index in range(1, 6)
    ]
    for product in DEMO_PRODUCTS:
        value = product["barcode"]
        weighted_sum = sum(
            int(digit) * (1 if index % 2 == 0 else 3)
            for index, digit in enumerate(value)
        )
        assert len(value) == 13
        assert weighted_sum % 10 == 0
