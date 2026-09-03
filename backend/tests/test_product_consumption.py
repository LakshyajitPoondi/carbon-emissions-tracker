"""Product scan -> explicit log -> summaries, history, authorization and units."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.consumption_record import ConsumptionRecord
from app.models.emission_calculation import EmissionCalculation
from app.services.reports import organization_report_totals
from app.ws import manager


def make_facility(client, org_id=None):
    if org_id is None:
        response = client.post("/api/organizations", json={"name": "Product consumption test", "industry_type": "manufacturing"})
        assert response.status_code == 201, response.text
        org_id = response.json()["id"]
    response = client.post("/api/facilities", json={
        "organization_id": org_id, "name": "Product test plant",
        "location": "Test location", "facility_type": "factory",
    })
    assert response.status_code == 201, response.text
    return response.json()


def product_body(org_id, **overrides):
    return {
        "organization_id": org_id, "name": "Test bottle", "composition": "Test aluminium",
        "emissions_value": "1.250000", "emissions_unit": "kg CO2e/item",
        "consumption_unit": "item", "consumption_source_type": "RESOURCE",
        "emissions_description": "Illustrative embodied emissions per bottle",
        "source_reference": "Test fixture, not a production factor", **overrides,
    }


def make_product(client, org_id, **overrides):
    response = client.post("/api/products", json=product_body(org_id, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


def log_body(product, facility, **overrides):
    return {
        "product_id": product["id"], "facility_id": facility["id"],
        "quantity_consumed": "2.0000", "unit": "item",
        "recorded_at": "2026-09-03T09:00:00Z", **overrides,
    }


def summary(client, facility, start="2026-09-03", end="2026-09-03"):
    response = client.get(f"/api/facilities/{facility['id']}/emissions-summary", params={"start_date": start, "end_date": end})
    assert response.status_code == 200, response.text
    return response.json()


def test_real_barcode_scan_is_read_only_then_explicit_log_updates_every_total(client, db_session):
    facility = make_facility(client)
    product = make_product(client, facility["organization_id"])
    image = client.get(f"/api/products/{product['id']}/barcode-image")
    before = summary(client, facility)
    assert before["total_emissions_kg_co2e"] == "0.00"
    scan = client.post(f"/api/facilities/{facility['id']}/asset-scan", files={"image": ("barcode.png", image.content, "image/png")})
    assert scan.status_code == 200, scan.text
    assert scan.json() == {"match_type": "product", "data": product}
    assert client.get("/api/consumption-records", params={"facility_id": facility["id"]}).json() == []

    response = client.post("/api/consumption-records", json=log_body(product, facility))
    assert response.status_code == 201, response.text
    record = response.json()
    assert set(record) == {"id", "emission_source_id", "product_id", "product_snapshot", "facility_id", "quantity_consumed", "unit", "recorded_at", "created_at", "calculation"}
    assert record["emission_source_id"] is None
    assert record["product_id"] == product["id"]
    assert record["product_snapshot"]["emissions_value"] == "1.250000"
    assert record["calculation"]["emission_factor_id"] is None
    assert record["calculation"]["calculated_emissions_kg_co2e"] == "2.5000"
    assert client.get("/api/consumption-records", params={"facility_id": facility["id"]}).json() == [record]
    after = summary(client, facility)
    assert after["by_source_type"] == {"ENERGY": "0.00", "FUEL": "0.00", "RESOURCE": "2.50"}
    assert after["total_emissions_kg_co2e"] == "2.50"
    assert summary(client, facility, "2026-09-04", "2026-09-05")["total_emissions_kg_co2e"] == "0.00"
    query = '''query($id: Int!) { organization(id: $id) { facilities {
      id emissionsSummary(startDate: "2026-09-03", endDate: "2026-09-03") {
        totalEmissionsKgCo2e bySourceType
      }
    } } }'''
    graphql = client.post("/graphql", json={"query": query, "variables": {"id": facility["organization_id"]}}).json()
    assert "errors" not in graphql, graphql
    overview = graphql["data"]["organization"]["facilities"][0]["emissionsSummary"]
    assert overview["totalEmissionsKgCo2e"] == "2.50"
    assert overview["bySourceType"] == after["by_source_type"]
    total, breakdown = organization_report_totals(db_session, facility["organization_id"], date(2026, 9, 3), date(2026, 9, 3))
    assert total == Decimal("2.50")
    assert breakdown[0]["total_emissions_kg_co2e"] == Decimal("2.50")
    report = client.post("/api/reports/generate", json={
        "organization_id": facility["organization_id"], "report_period_start": "2026-09-03", "report_period_end": "2026-09-03",
    })
    assert report.status_code == 201, report.text
    final = client.get(f"/api/reports/{report.json()['id']}").json()
    assert final["total_emissions_kg_co2e"] == "2.50"


def test_history_and_totals_survive_product_edit_disable_and_delete(client):
    facility = make_facility(client)
    product = make_product(client, facility["organization_id"])
    response = client.post("/api/consumption-records", json=log_body(product, facility))
    assert response.status_code == 201, response.text
    original = response.json()
    updated = client.patch(f"/api/products/{product['id']}", json={
        "name": "Different name", "emissions_value": "99", "consumption_source_type": "FUEL",
    })
    assert updated.status_code == 200, updated.text
    assert client.patch(f"/api/products/{product['id']}", json={"consumption_unit": None, "consumption_source_type": None}).status_code == 200
    assert client.delete(f"/api/products/{product['id']}").status_code == 204
    saved = client.get("/api/consumption-records", params={"facility_id": facility["id"]}).json()[0]
    assert saved["product_id"] is None
    assert saved["product_snapshot"] == original["product_snapshot"]
    assert saved["calculation"] == original["calculation"]
    assert summary(client, facility)["by_source_type"]["RESOURCE"] == "2.50"


@pytest.mark.parametrize("role", ["OWNER", "ADMIN", "EMPLOYEE"])
def test_all_member_roles_can_log_and_receive_live_event(client, other_client, other_user, grant_membership, role):
    facility = make_facility(client)
    product = make_product(client, facility["organization_id"])
    grant_membership(other_user.id, facility["organization_id"], role)
    messages = []

    class Socket:
        async def send_json(self, message):
            messages.append(message)

    socket = Socket()
    channel = f"facility:{facility['id']}"
    manager.connect(channel, socket)
    try:
        response = other_client.post("/api/consumption-records", json=log_body(product, facility))
        assert response.status_code == 201, response.text
        assert messages == [{"type": "consumption_record_created", "consumption_record": response.json()}]
    finally:
        manager.disconnect(channel, socket)


def test_cross_organization_pair_and_nonmember_are_masked(client, other_client):
    facility = make_facility(client)
    other_facility = make_facility(client)
    product = make_product(client, facility["organization_id"])
    for caller, target in [(client, other_facility), (other_client, facility)]:
        response = caller.post("/api/consumption-records", json=log_body(product, target))
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("overrides", [
    {"quantity_consumed": "0"}, {"quantity_consumed": "-1"},
    {"quantity_consumed": "0.00001"}, {"quantity_consumed": "NaN"},
    {"quantity_consumed": "10000000000"}, {"quantity_consumed": "9999999999.9999"},
    {"recorded_at": "2026-09-03T09:00:00"}, {"emission_source_id": 1}, {"product_id": None},
])
def test_invalid_input_never_writes_records_or_calculations(client, db_session, overrides):
    facility = make_facility(client)
    product = make_product(client, facility["organization_id"])
    counts = (db_session.query(ConsumptionRecord).count(), db_session.query(EmissionCalculation).count())
    response = client.post("/api/consumption-records", json=log_body(product, facility, **overrides))
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert (db_session.query(ConsumptionRecord).count(), db_session.query(EmissionCalculation).count()) == counts


def test_reference_only_and_wrong_units_fail_clearly(client):
    facility = make_facility(client)
    product = make_product(client, facility["organization_id"], consumption_unit=None, consumption_source_type=None)
    response = client.post("/api/consumption-records", json=log_body(product, facility))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PRODUCT_NOT_CONFIGURED"
    configured = client.patch(f"/api/products/{product['id']}", json={"consumption_unit": "item", "consumption_source_type": "RESOURCE"})
    assert configured.status_code == 200
    mismatch = client.post("/api/consumption-records", json=log_body(product, facility, unit="kg"))
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "PRODUCT_UNIT_MISMATCH"


@pytest.mark.parametrize("overrides", [
    {"consumption_unit": None}, {"consumption_source_type": None},
    {"consumption_source_type": "OTHER"}, {"consumption_unit": " "},
    {"emissions_unit": "g CO2e/item"}, {"emissions_unit": "kg CO2e per item"},
])
def test_invalid_product_configuration_is_rejected(client, overrides):
    facility = make_facility(client)
    response = client.post("/api/products", json=product_body(facility["organization_id"], **overrides))
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_patch_validates_merged_configuration_and_employee_cannot_enable(client, other_client, other_user, grant_membership):
    facility = make_facility(client)
    product = make_product(client, facility["organization_id"])
    invalid = client.patch(f"/api/products/{product['id']}", json={"consumption_unit": "kg"})
    assert invalid.status_code == 422
    assert client.get(f"/api/products/{product['id']}").json()["consumption_unit"] == "item"
    grant_membership(other_user.id, facility["organization_id"], "EMPLOYEE")
    assert other_client.patch(f"/api/products/{product['id']}", json={"consumption_source_type": "FUEL"}).status_code == 404


def test_product_decimal_rounding_is_half_up_and_zero_factor_is_valid(client):
    facility = make_facility(client)
    product = make_product(client, facility["organization_id"], emissions_value="0.123450")
    response = client.post("/api/consumption-records", json=log_body(product, facility, quantity_consumed="1"))
    assert response.status_code == 201, response.text
    assert response.json()["calculation"]["calculated_emissions_kg_co2e"] == "0.1235"
    assert client.patch(f"/api/products/{product['id']}", json={"emissions_value": "0"}).status_code == 200
    zero = client.post("/api/consumption-records", json=log_body(product, facility, quantity_consumed="1"))
    assert zero.status_code == 201
    assert zero.json()["calculation"]["calculated_emissions_kg_co2e"] == "0.0000"


def test_database_enforces_product_facility_organization_link(client, db_session):
    first = make_facility(client)
    second = make_facility(client)
    product = make_product(client, first["organization_id"])
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(ConsumptionRecord(
                product_id=product["id"], product_organization_id=first["organization_id"],
                product_snapshot=product, product_source_type="RESOURCE", facility_id=second["id"],
                quantity_consumed=Decimal("1"), unit="item", recorded_at=datetime.now(timezone.utc),
            ))
            db_session.flush()
