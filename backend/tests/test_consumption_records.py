"""Tests for POST/GET /api/consumption-records — the emissions calculation path."""

from decimal import Decimal


def _make_facility_and_source(client, source_type="ENERGY"):
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
    facility_id = fac_resp.json()["id"]

    source_resp = client.post(
        "/api/emission-sources",
        json={
            "facility_id": facility_id,
            "source_type": source_type,
            "source_name": "Grid electricity",
            "unit_of_measurement": "kWh",
        },
    )
    source_id = source_resp.json()["id"]

    return facility_id, source_id


class TestCreateConsumptionRecord:
    def test_success_computes_emissions(self, client):
        facility_id, source_id = _make_facility_and_source(client)

        resp = client.post(
            "/api/consumption-records",
            json={
                "emission_source_id": source_id,
                "facility_id": facility_id,
                "quantity_consumed": "1000",
                "unit": "kWh",
                "recorded_at": "2026-08-20T00:00:00Z",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["emission_source_id"] == source_id
        assert data["facility_id"] == facility_id
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" not in data

        calc = data["calculation"]
        assert calc is not None
        # 1000 kWh * 0.708200 kg_co2e_per_kwh (seeded IN/ENERGY factor)
        assert Decimal(calc["calculated_emissions_kg_co2e"]) == Decimal("708.2000")
        assert calc["calculation_date"] is not None

    def test_nonexistent_emission_source_returns_404(self, client):
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
            "/api/consumption-records",
            json={
                "emission_source_id": 99999,
                "facility_id": facility_id,
                "quantity_consumed": "10",
                "unit": "kWh",
                "recorded_at": "2026-08-20T00:00:00Z",
            },
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    def test_nonexistent_facility_returns_404(self, client):
        _facility_id, source_id = _make_facility_and_source(client)

        resp = client.post(
            "/api/consumption-records",
            json={
                "emission_source_id": source_id,
                "facility_id": 99999,
                "quantity_consumed": "10",
                "unit": "kWh",
                "recorded_at": "2026-08-20T00:00:00Z",
            },
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    def test_no_matching_factor_returns_422(self, client):
        # Seeded factors are only valid_from 2026-01-01 onward — a date
        # before that has no applicable factor.
        facility_id, source_id = _make_facility_and_source(client)

        resp = client.post(
            "/api/consumption-records",
            json={
                "emission_source_id": source_id,
                "facility_id": facility_id,
                "quantity_consumed": "10",
                "unit": "kWh",
                "recorded_at": "2020-01-01T00:00:00Z",
            },
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "NO_MATCHING_FACTOR"


class TestListConsumptionRecords:
    def test_lists_records_for_facility_with_calculation(self, client):
        facility_id, source_id = _make_facility_and_source(client)

        client.post(
            "/api/consumption-records",
            json={
                "emission_source_id": source_id,
                "facility_id": facility_id,
                "quantity_consumed": "500",
                "unit": "kWh",
                "recorded_at": "2026-08-10T00:00:00Z",
            },
        )
        client.post(
            "/api/consumption-records",
            json={
                "emission_source_id": source_id,
                "facility_id": facility_id,
                "quantity_consumed": "250",
                "unit": "kWh",
                "recorded_at": "2026-08-20T00:00:00Z",
            },
        )

        resp = client.get("/api/consumption-records", params={"facility_id": facility_id})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert all(row["calculation"] is not None for row in data)

    def test_filters_by_date_range(self, client):
        facility_id, source_id = _make_facility_and_source(client)

        client.post(
            "/api/consumption-records",
            json={
                "emission_source_id": source_id,
                "facility_id": facility_id,
                "quantity_consumed": "500",
                "unit": "kWh",
                "recorded_at": "2026-08-01T00:00:00Z",
            },
        )
        client.post(
            "/api/consumption-records",
            json={
                "emission_source_id": source_id,
                "facility_id": facility_id,
                "quantity_consumed": "250",
                "unit": "kWh",
                "recorded_at": "2026-08-20T00:00:00Z",
            },
        )

        resp = client.get(
            "/api/consumption-records",
            params={"facility_id": facility_id, "start_date": "2026-08-15", "end_date": "2026-08-25"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["quantity_consumed"] == "250.0000"
