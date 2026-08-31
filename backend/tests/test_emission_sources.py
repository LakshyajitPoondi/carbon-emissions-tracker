"""Tests for creating and updating emission sources."""

from app.models.organization_member import ROLE_EMPLOYEE


class TestCreateEmissionSource:
    def test_invalid_source_type_returns_422(self, client):
        # Create org + facility first so facility_id is valid
        org_resp = client.post(
            "/api/organizations",
            json={"name": "Acme Corp", "industry_type": "manufacturing"},
        )
        org_id = org_resp.json()["id"]

        fac_resp = client.post(
            "/api/facilities",
            json={
                "organization_id": org_id,
                "name": "Plant A",
                "location": "Chennai, TN",
                "facility_type": "factory",
            },
        )
        facility_id = fac_resp.json()["id"]

        resp = client.post(
            "/api/emission-sources",
            json={
                "facility_id": facility_id,
                "source_type": "INVALID_TYPE",
                "source_name": "Bad source",
                "unit_of_measurement": "kWh",
            },
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_barcode_value_optional_and_returned(self, client):
        org_resp = client.post(
            "/api/organizations", json={"name": "Barcode Corp", "industry_type": "manufacturing"}
        )
        org_id = org_resp.json()["id"]
        fac_resp = client.post(
            "/api/facilities",
            json={
                "organization_id": org_id,
                "name": "Plant B",
                "location": "Chennai, TN",
                "facility_type": "factory",
            },
        )
        facility_id = fac_resp.json()["id"]

        no_barcode = client.post(
            "/api/emission-sources",
            json={
                "facility_id": facility_id,
                "source_type": "ENERGY",
                "source_name": "Grid electricity",
                "unit_of_measurement": "kWh",
            },
        )
        assert no_barcode.status_code == 201
        assert no_barcode.json()["barcode_value"] is None

        with_barcode = client.post(
            "/api/emission-sources",
            json={
                "facility_id": facility_id,
                "source_type": "FUEL",
                "source_name": "Diesel generator",
                "unit_of_measurement": "litre",
                "barcode_value": "ENSRC-B-001",
            },
        )
        assert with_barcode.status_code == 201
        assert with_barcode.json()["barcode_value"] == "ENSRC-B-001"

    def test_duplicate_barcode_in_same_facility_returns_422(self, client):
        org_id = client.post(
            "/api/organizations", json={"name": "Dup Corp", "industry_type": "manufacturing"}
        ).json()["id"]
        facility_id = client.post(
            "/api/facilities",
            json={
                "organization_id": org_id,
                "name": "Plant C",
                "location": "Chennai, TN",
                "facility_type": "factory",
            },
        ).json()["id"]

        first = client.post(
            "/api/emission-sources",
            json={
                "facility_id": facility_id,
                "source_type": "ENERGY",
                "source_name": "Grid electricity",
                "unit_of_measurement": "kWh",
                "barcode_value": "DUPLICATE-001",
            },
        )
        assert first.status_code == 201

        second = client.post(
            "/api/emission-sources",
            json={
                "facility_id": facility_id,
                "source_type": "FUEL",
                "source_name": "Diesel generator",
                "unit_of_measurement": "litre",
                "barcode_value": "DUPLICATE-001",
            },
        )
        assert second.status_code == 422
        assert second.json()["error"]["code"] == "BARCODE_ALREADY_ASSIGNED"


def _source_tree(client):
    organization = client.post(
        "/api/organizations",
        json={"name": "Source Update Org", "industry_type": "manufacturing"},
    ).json()
    facility = client.post(
        "/api/facilities",
        json={
            "organization_id": organization["id"],
            "name": "Source Update Facility",
            "location": "Chennai, TN",
            "facility_type": "factory",
        },
    ).json()
    source = client.post(
        "/api/emission-sources",
        json={
            "facility_id": facility["id"],
            "source_type": "ENERGY",
            "source_name": "Grid electricity",
            "unit_of_measurement": "kWh",
        },
    ).json()
    return organization, facility, source


class TestUpdateEmissionSource:
    def test_sets_and_clears_barcode_value(self, client):
        _, _, source = _source_tree(client)

        set_barcode = client.patch(
            f"/api/emission-sources/{source['id']}",
            json={"barcode_value": "MANUAL-BARCODE-001"},
        )
        assert set_barcode.status_code == 200
        assert set_barcode.json()["barcode_value"] == "MANUAL-BARCODE-001"
        listed = client.get(
            "/api/emission-sources",
            params={"facility_id": set_barcode.json()["facility_id"]},
        )
        assert listed.status_code == 200
        assert listed.json()[0]["barcode_value"] == "MANUAL-BARCODE-001"

        clear_barcode = client.patch(
            f"/api/emission-sources/{source['id']}",
            json={"barcode_value": None},
        )
        assert clear_barcode.status_code == 200
        assert clear_barcode.json()["barcode_value"] is None

    def test_duplicate_barcode_update_returns_422(self, client):
        _, facility, source = _source_tree(client)
        other = client.post(
            "/api/emission-sources",
            json={
                "facility_id": facility["id"],
                "source_type": "FUEL",
                "source_name": "Diesel",
                "unit_of_measurement": "litre",
                "barcode_value": "ALREADY-USED",
            },
        ).json()

        response = client.patch(
            f"/api/emission-sources/{source['id']}",
            json={"barcode_value": other["barcode_value"]},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "BARCODE_ALREADY_ASSIGNED"

    def test_employee_update_is_masked_as_not_found(
        self, client, other_client, other_user, grant_membership
    ):
        organization, _, source = _source_tree(client)
        grant_membership(other_user.id, organization["id"], ROLE_EMPLOYEE)

        response = other_client.patch(
            f"/api/emission-sources/{source['id']}",
            json={"barcode_value": "EMPLOYEE-CANNOT-WRITE"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"
