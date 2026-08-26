"""Tests for POST /api/emission-sources — invalid source_type returns 422."""


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
