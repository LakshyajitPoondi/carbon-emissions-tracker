"""Tests for GET /ws/organizations/{organization_id} — the Celery-worker-
to-WebSocket bridge for report_generated broadcasts (see app/pubsub.py).

Requires a real Redis connection, unlike the rest of the suite (which runs
with SKIP_PUBSUB=true — see conftest.py) since this specifically tests that
bridge. Uses a fresh TestClient with SKIP_PUBSUB unset for its own scope,
the same pattern test_asset_scan.py uses for the "model loaded once at
startup" test.
"""

import time

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app


class TestReportWebSocketBridge:
    def test_receives_report_generated_after_task_completes(self, db_session, monkeypatch):
        monkeypatch.delenv("SKIP_PUBSUB", raising=False)

        def _override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = _override_get_db
        try:
            with TestClient(app) as c:
                # Give the lifespan's background Redis subscriber a moment
                # to actually complete its SUBSCRIBE before anything gets
                # published — Redis pub/sub doesn't replay missed messages,
                # so publishing before the subscription is live would be a
                # silent, order-dependent loss, not a retryable failure.
                time.sleep(0.5)

                email = "wsreport@example.com"
                password = "wsreportpass123"
                register = c.post("/api/auth/register", json={"email": email, "password": password})
                assert register.status_code == 201, register.text
                token = c.post(
                    "/api/auth/token", data={"username": email, "password": password}
                ).json()["access_token"]
                c.headers["Authorization"] = f"Bearer {token}"

                org = c.post(
                    "/api/organizations",
                    json={"name": "WS Report Co", "industry_type": "manufacturing"},
                ).json()

                with c.websocket_connect(f"/ws/organizations/{org['id']}?token={token}") as ws:
                    gen_resp = c.post(
                        "/api/reports/generate",
                        json={
                            "organization_id": org["id"],
                            "report_period_start": "2026-08-01",
                            "report_period_end": "2026-08-26",
                        },
                    )
                    assert gen_resp.status_code == 201
                    report_id = gen_resp.json()["id"]

                    message = ws.receive_json()

                assert message["type"] == "report_generated"
                assert message["report"]["id"] == report_id
                assert message["report"]["status"] == "final"
                assert message["report"]["total_emissions_kg_co2e"] == "0.00"
        finally:
            app.dependency_overrides.pop(get_db, None)
