"""Tests for GET /api/facilities/{id}/emissions-summary — dashboard aggregation."""


def _make_org_and_facility(client):
    org_resp = client.post(
        "/api/organizations",
        json={"name": "Acme Corp", "industry_type": "manufacturing"},
    )
    org_id = org_resp.json()["id"]
    fac_resp = client.post(
        "/api/facilities",
        json={
            "organization_id": org_id,
            "name": "Chennai Plant",
            "location": "Chennai, TN",
            "facility_type": "factory",
        },
    )
    return org_id, fac_resp.json()["id"]


def _make_source(client, facility_id, source_type):
    resp = client.post(
        "/api/emission-sources",
        json={
            "facility_id": facility_id,
            "source_type": source_type,
            "source_name": f"{source_type} source",
            "unit_of_measurement": "unit",
        },
    )
    return resp.json()["id"]


class TestEmissionsSummary:
    def test_aggregates_by_source_type(self, client):
        _org_id, facility_id = _make_org_and_facility(client)
        energy_source = _make_source(client, facility_id, "ENERGY")
        fuel_source = _make_source(client, facility_id, "FUEL")

        client.post(
            "/api/consumption-records",
            json={
                "emission_source_id": energy_source,
                "facility_id": facility_id,
                "quantity_consumed": "1000",
                "unit": "kWh",
                "recorded_at": "2026-08-05T00:00:00Z",
            },
        )
        client.post(
            "/api/consumption-records",
            json={
                "emission_source_id": fuel_source,
                "facility_id": facility_id,
                "quantity_consumed": "100",
                "unit": "litre",
                "recorded_at": "2026-08-15T00:00:00Z",
            },
        )

        resp = client.get(
            f"/api/facilities/{facility_id}/emissions-summary",
            params={"start_date": "2026-08-01", "end_date": "2026-08-26"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["facility_id"] == facility_id
        assert data["period"] == {"start": "2026-08-01", "end": "2026-08-26"}
        assert data["by_source_type"]["ENERGY"] == "708.20"
        assert data["by_source_type"]["FUEL"] == "268.30"
        assert data["by_source_type"]["RESOURCE"] == "0.00"
        assert data["total_emissions_kg_co2e"] == "976.50"

    def test_excludes_records_outside_period(self, client):
        _org_id, facility_id = _make_org_and_facility(client)
        energy_source = _make_source(client, facility_id, "ENERGY")

        client.post(
            "/api/consumption-records",
            json={
                "emission_source_id": energy_source,
                "facility_id": facility_id,
                "quantity_consumed": "1000",
                "unit": "kWh",
                "recorded_at": "2026-01-01T00:00:00Z",
            },
        )

        resp = client.get(
            f"/api/facilities/{facility_id}/emissions-summary",
            params={"start_date": "2026-08-01", "end_date": "2026-08-26"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_emissions_kg_co2e"] == "0.00"

    def test_nonexistent_facility_returns_404(self, client):
        resp = client.get(
            "/api/facilities/99999/emissions-summary",
            params={"start_date": "2026-08-01", "end_date": "2026-08-26"},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    def test_missing_date_params_returns_422(self, client):
        _org_id, facility_id = _make_org_and_facility(client)
        resp = client.get(f"/api/facilities/{facility_id}/emissions-summary")
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
