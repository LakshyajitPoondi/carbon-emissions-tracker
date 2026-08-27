"""Tests for GET /ws/facilities/{facility_id}.

Covers: connection succeeds with a valid token, is rejected without one, and
a connected client receives the expected broadcast after a consumption
record is created for its facility.
"""

import pytest
from starlette.websockets import WebSocketDisconnect


def _create_org_facility_source(client):
    org = client.post(
        "/api/organizations", json={"name": "WS Co", "industry_type": "manufacturing"}
    ).json()
    facility = client.post(
        "/api/facilities",
        json={
            "organization_id": org["id"],
            "name": "WS Plant",
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
    return org, facility, source


def _token(client) -> str:
    return client.headers["Authorization"].split(" ", 1)[1]


class TestWebSocketAuth:
    def test_connect_with_valid_token_succeeds(self, client):
        _, facility, _ = _create_org_facility_source(client)
        token = _token(client)
        with client.websocket_connect(f"/ws/facilities/{facility['id']}?token={token}"):
            pass  # connecting and cleanly exiting the context is the assertion

    def test_connect_without_token_rejected(self, client):
        _, facility, _ = _create_org_facility_source(client)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/ws/facilities/{facility['id']}") as ws:
                ws.receive_text()
        assert exc_info.value.code == 1008

    def test_connect_with_invalid_token_rejected(self, client):
        _, facility, _ = _create_org_facility_source(client)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                f"/ws/facilities/{facility['id']}?token=not-a-real-token"
            ) as ws:
                ws.receive_text()
        assert exc_info.value.code == 1008

    def test_connect_to_nonexistent_facility_rejected(self, client):
        token = _token(client)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/ws/facilities/999999?token={token}") as ws:
                ws.receive_text()
        assert exc_info.value.code == 4004


class TestWebSocketBroadcast:
    def test_receives_broadcast_after_consumption_record_created(self, client):
        _, facility, source = _create_org_facility_source(client)
        token = _token(client)

        with client.websocket_connect(f"/ws/facilities/{facility['id']}?token={token}") as ws:
            resp = client.post(
                "/api/consumption-records",
                json={
                    "emission_source_id": source["id"],
                    "facility_id": facility["id"],
                    "quantity_consumed": "100.000000",
                    "unit": "kWh",
                    "recorded_at": "2026-08-20T00:00:00Z",
                },
            )
            assert resp.status_code == 201
            record = resp.json()

            message = ws.receive_json()

        assert message["type"] == "consumption_record_created"
        assert message["consumption_record"]["id"] == record["id"]
        assert (
            message["consumption_record"]["calculation"]["calculated_emissions_kg_co2e"]
            == record["calculation"]["calculated_emissions_kg_co2e"]
        )

    def test_client_on_a_different_facility_does_not_receive_it(self, client):
        """A broadcast for facility_a must not reach a client connected to
        facility_b. Verified deterministically (no blind blocking-receive
        that could hang or race): trigger a facility_a broadcast first, then
        a facility_b broadcast, then assert the *first* message the
        facility_b socket receives is the facility_b one — proving the
        facility_a broadcast was never delivered to it."""
        _, facility_a, source_a = _create_org_facility_source(client)
        _, facility_b, source_b = _create_org_facility_source(client)
        token = _token(client)

        with client.websocket_connect(f"/ws/facilities/{facility_b['id']}?token={token}") as ws:
            client.post(
                "/api/consumption-records",
                json={
                    "emission_source_id": source_a["id"],
                    "facility_id": facility_a["id"],
                    "quantity_consumed": "50.000000",
                    "unit": "kWh",
                    "recorded_at": "2026-08-20T00:00:00Z",
                },
            )
            resp_b = client.post(
                "/api/consumption-records",
                json={
                    "emission_source_id": source_b["id"],
                    "facility_id": facility_b["id"],
                    "quantity_consumed": "75.000000",
                    "unit": "kWh",
                    "recorded_at": "2026-08-20T00:00:00Z",
                },
            )
            record_b = resp_b.json()
            message = ws.receive_json()

        assert message["consumption_record"]["id"] == record_b["id"]
