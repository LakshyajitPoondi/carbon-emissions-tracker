"""Tests for POST /api/reports/generate, GET /api/reports/{id}, GET /api/reports."""


def _make_org(client):
    resp = client.post(
        "/api/organizations",
        json={"name": "Acme Corp", "industry_type": "manufacturing"},
    )
    return resp.json()["id"]


def _make_facility(client, org_id, name="Chennai Plant"):
    resp = client.post(
        "/api/facilities",
        json={
            "organization_id": org_id,
            "name": name,
            "location": "Chennai, TN",
            "facility_type": "factory",
        },
    )
    return resp.json()["id"]


def _make_source(client, facility_id, source_type="ENERGY"):
    resp = client.post(
        "/api/emission-sources",
        json={
            "facility_id": facility_id,
            "source_type": source_type,
            "source_name": "Grid electricity",
            "unit_of_measurement": "kWh",
        },
    )
    return resp.json()["id"]


class TestGenerateReport:
    def test_success_with_facility_breakdown(self, client):
        org_id = _make_org(client)
        facility_id = _make_facility(client, org_id)
        source_id = _make_source(client, facility_id)

        client.post(
            "/api/consumption-records",
            json={
                "emission_source_id": source_id,
                "facility_id": facility_id,
                "quantity_consumed": "1000",
                "unit": "kWh",
                "recorded_at": "2026-08-10T00:00:00Z",
            },
        )

        resp = client.post(
            "/api/reports/generate",
            json={
                "organization_id": org_id,
                "report_period_start": "2026-08-01",
                "report_period_end": "2026-08-26",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["organization_id"] == org_id
        assert data["status"] == "final"
        assert data["total_emissions_kg_co2e"] == "708.20"
        assert data["facilities"] == [
            {"facility_id": facility_id, "facility_name": "Chennai Plant", "total_emissions_kg_co2e": "708.20"}
        ]

    def test_facility_with_no_records_reports_zero(self, client):
        org_id = _make_org(client)
        _make_facility(client, org_id, name="Empty Plant")

        resp = client.post(
            "/api/reports/generate",
            json={
                "organization_id": org_id,
                "report_period_start": "2026-08-01",
                "report_period_end": "2026-08-26",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["total_emissions_kg_co2e"] == "0.00"
        assert data["facilities"][0]["total_emissions_kg_co2e"] == "0.00"

    def test_nonexistent_organization_returns_404(self, client):
        resp = client.post(
            "/api/reports/generate",
            json={
                "organization_id": 99999,
                "report_period_start": "2026-08-01",
                "report_period_end": "2026-08-26",
            },
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"


class TestGetReport:
    def test_get_matches_generated_report(self, client):
        org_id = _make_org(client)
        facility_id = _make_facility(client, org_id)
        source_id = _make_source(client, facility_id)
        client.post(
            "/api/consumption-records",
            json={
                "emission_source_id": source_id,
                "facility_id": facility_id,
                "quantity_consumed": "1000",
                "unit": "kWh",
                "recorded_at": "2026-08-10T00:00:00Z",
            },
        )
        gen_resp = client.post(
            "/api/reports/generate",
            json={
                "organization_id": org_id,
                "report_period_start": "2026-08-01",
                "report_period_end": "2026-08-26",
            },
        )
        report_id = gen_resp.json()["id"]

        resp = client.get(f"/api/reports/{report_id}")
        assert resp.status_code == 200
        assert resp.json() == gen_resp.json()

    def test_not_found(self, client):
        resp = client.get("/api/reports/99999")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"


class TestListReports:
    def test_list_omits_facilities_breakdown(self, client):
        org_id = _make_org(client)
        _make_facility(client, org_id)
        client.post(
            "/api/reports/generate",
            json={
                "organization_id": org_id,
                "report_period_start": "2026-08-01",
                "report_period_end": "2026-08-26",
            },
        )

        resp = client.get("/api/reports", params={"organization_id": org_id})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert "facilities" not in data[0]
        assert "total_emissions_kg_co2e" in data[0]
        assert data[0]["status"] == "final"
