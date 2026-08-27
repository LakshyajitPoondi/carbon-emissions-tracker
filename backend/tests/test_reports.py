"""Tests for POST /api/reports/generate, GET /api/reports/{id}, GET /api/reports.

Generation is async (Celery). The test suite runs Celery in eager mode (see
conftest.py) — .delay() executes the task synchronously in-process, so by
the time a test's POST call returns, the report row has already been
updated to FINAL in the database. The route handler is deliberately built
to still respond with PENDING regardless (see reports.py's comment) — these
tests check that explicitly, then use a separate GET to observe the result
of the (already-completed, in eager mode) task.
"""

from app.models.report import Report, ReportStatusEnum


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
    def test_returns_pending_immediately(self, client):
        """The POST response must always be PENDING with no totals yet —
        even though eager-mode Celery has, by this point, already finished
        the task behind the scenes. See reports.py's comment: the response
        is built from pre-dispatch state on purpose, not re-fetched."""
        org_id = _make_org(client)
        _make_facility(client, org_id)

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
        assert data["status"] == "pending"
        assert data["total_emissions_kg_co2e"] is None
        assert data["facilities"] is None

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


class TestReportTaskExecution:
    """Verifies the Celery task itself actually reaches FINAL with correct
    totals — the thing the PENDING response above deliberately doesn't show."""

    def test_task_reaches_final_with_correct_totals(self, client):
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

        get_resp = client.get(f"/api/reports/{report_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["status"] == "final"
        assert data["total_emissions_kg_co2e"] == "708.20"
        assert data["facilities"] == [
            {"facility_id": facility_id, "facility_name": "Chennai Plant", "total_emissions_kg_co2e": "708.20"}
        ]

    def test_facility_with_no_records_reports_zero(self, client):
        org_id = _make_org(client)
        _make_facility(client, org_id, name="Empty Plant")

        gen_resp = client.post(
            "/api/reports/generate",
            json={
                "organization_id": org_id,
                "report_period_start": "2026-08-01",
                "report_period_end": "2026-08-26",
            },
        )
        report_id = gen_resp.json()["id"]

        data = client.get(f"/api/reports/{report_id}").json()
        assert data["status"] == "final"
        assert data["total_emissions_kg_co2e"] == "0.00"
        assert data["facilities"][0]["total_emissions_kg_co2e"] == "0.00"


class TestGetReport:
    def test_pending_report_has_no_totals(self, client, db_session):
        """A report GET'd before the task runs must show pending with null
        totals — construct that state directly rather than racing a real
        async task, since eager-mode Celery would otherwise have already
        finished it by the time any GET could observe PENDING."""
        org_id = _make_org(client)

        report = Report(
            organization_id=org_id,
            report_period_start="2026-08-01",
            report_period_end="2026-08-26",
            status=ReportStatusEnum.PENDING,
        )
        db_session.add(report)
        db_session.commit()
        db_session.refresh(report)

        resp = client.get(f"/api/reports/{report.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["total_emissions_kg_co2e"] is None
        assert data["facilities"] is None

    def test_processing_report_has_no_totals(self, client, db_session):
        org_id = _make_org(client)
        report = Report(
            organization_id=org_id,
            report_period_start="2026-08-01",
            report_period_end="2026-08-26",
            status=ReportStatusEnum.PROCESSING,
        )
        db_session.add(report)
        db_session.commit()
        db_session.refresh(report)

        resp = client.get(f"/api/reports/{report.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "processing"
        assert data["total_emissions_kg_co2e"] is None
        assert data["facilities"] is None

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

        # gen_resp itself is PENDING (see TestGenerateReport); the GET
        # reflects the (already, in eager mode) completed task instead.
        resp = client.get(f"/api/reports/{report_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "final"

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
        # Eager-mode Celery has already finished the task by the time this
        # list is fetched.
        assert data[0]["status"] == "final"
        assert data[0]["total_emissions_kg_co2e"] == "0.00"
