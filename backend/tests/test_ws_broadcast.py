"""Broadcast safety: a bad WebSocket client must not damage anything else.

The three failure modes fixed here all had the same shape — a problem with
one subscriber becoming a problem for the request that triggered the
broadcast, or for the other subscribers.

The stakes on the first one are worth stating: broadcasts fire from HTTP
handlers *after* the database write has committed. If a dead client could
raise back into the handler, a record that was successfully saved would be
reported to the caller as a failure — and a caller that retries a write it
believes failed creates a duplicate record. A courtesy notification must
never be able to rewrite the outcome of the request that caused it.

These use asyncio.run rather than an async test plugin: the suite has none,
and broadcast() is directly callable.
"""

import asyncio

import pytest

from app import ws as ws_module
from app.ws import ConnectionManager, manager


class FakeSocket:
    """Records what it received."""

    def __init__(self, name: str = "ok"):
        self.name = name
        self.received: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.received.append(message)


class ExplodingSocket(FakeSocket):
    """A client that dropped without a clean close frame reaching us."""

    async def send_json(self, message: dict) -> None:
        raise RuntimeError("connection is gone")


class HangingSocket(FakeSocket):
    """A client that accepted the connection and then stopped reading."""

    def __init__(self, name: str = "hanging"):
        super().__init__(name)
        self.started = False

    async def send_json(self, message: dict) -> None:
        self.started = True
        await asyncio.sleep(3600)


class DisconnectingSocket(FakeSocket):
    """Mutates the live connection set from inside the broadcast loop."""

    def __init__(self, mgr: ConnectionManager, channel: str, victim: FakeSocket):
        super().__init__("disconnector")
        self._manager = mgr
        self._channel = channel
        self._victim = victim

    async def send_json(self, message: dict) -> None:
        self.received.append(message)
        self._manager.disconnect(self._channel, self._victim)


def _channel_size(mgr: ConnectionManager, channel: str) -> int:
    return len(mgr._connections.get(channel, ()))


class TestOneBadClientCannotHarmTheOthers:
    def test_broadcast_never_raises_when_a_send_fails(self):
        mgr = ConnectionManager()
        bad = ExplodingSocket("bad")
        mgr.connect("facility:1", bad)

        # No pytest.raises — the assertion is that this simply returns.
        asyncio.run(mgr.broadcast("facility:1", {"type": "ping"}))

    def test_other_clients_still_receive_the_message(self):
        mgr = ConnectionManager()
        good_before, bad, good_after = FakeSocket("first"), ExplodingSocket(), FakeSocket("last")
        for socket in (good_before, bad, good_after):
            mgr.connect("facility:1", socket)

        asyncio.run(mgr.broadcast("facility:1", {"type": "ping"}))

        assert good_before.received == [{"type": "ping"}]
        assert good_after.received == [{"type": "ping"}]

    def test_the_failing_client_is_dropped_not_merely_skipped(self):
        """Left connected, it would be retried on every future broadcast —
        paying the full timeout each time, forever."""
        mgr = ConnectionManager()
        good, bad = FakeSocket(), ExplodingSocket()
        mgr.connect("facility:1", good)
        mgr.connect("facility:1", bad)

        asyncio.run(mgr.broadcast("facility:1", {"type": "ping"}))

        assert _channel_size(mgr, "facility:1") == 1
        assert good in mgr._connections["facility:1"]
        assert bad not in mgr._connections["facility:1"]


class TestDisconnectDuringBroadcast:
    def test_a_client_disconnecting_mid_broadcast_does_not_crash(self):
        """Iterating the live set would raise "Set changed size during
        iteration" here, turning an ordinary disconnect into a failed
        request. The snapshot is what prevents it."""
        mgr = ConnectionManager()
        victim = FakeSocket("victim")
        survivor = FakeSocket("survivor")
        disconnector = DisconnectingSocket(mgr, "facility:1", victim)
        for socket in (victim, disconnector, survivor):
            mgr.connect("facility:1", socket)

        asyncio.run(mgr.broadcast("facility:1", {"type": "ping"}))

        assert survivor.received == [{"type": "ping"}]
        assert victim not in mgr._connections.get("facility:1", set())


class TestStalledClientTimeout:
    def test_a_hanging_client_is_dropped_rather_than_blocking(self, monkeypatch):
        monkeypatch.setattr(ws_module, "BROADCAST_SEND_TIMEOUT_SECONDS", 0.05)

        mgr = ConnectionManager()
        stalled = HangingSocket()
        healthy = FakeSocket("healthy")
        mgr.connect("facility:1", stalled)
        mgr.connect("facility:1", healthy)

        async def run_and_time():
            loop = asyncio.get_running_loop()
            started = loop.time()
            await mgr.broadcast("facility:1", {"type": "ping"})
            return loop.time() - started

        elapsed = asyncio.run(run_and_time())

        assert stalled.started, "the stalled send should have been attempted"
        # Bounded by the timeout, not by the client (which sleeps for an hour).
        assert elapsed < 1.0
        assert stalled not in mgr._connections.get("facility:1", set())
        assert healthy.received == [{"type": "ping"}]

    def test_a_stalled_client_does_not_delay_healthy_ones(self, monkeypatch):
        """Sends run concurrently, so the fan-out is bounded by the timeout
        rather than by the sum of every slow client."""
        monkeypatch.setattr(ws_module, "BROADCAST_SEND_TIMEOUT_SECONDS", 0.05)

        mgr = ConnectionManager()
        for index in range(5):
            mgr.connect("facility:1", HangingSocket(f"stalled-{index}"))
        healthy = FakeSocket("healthy")
        mgr.connect("facility:1", healthy)

        async def run_and_time():
            loop = asyncio.get_running_loop()
            started = loop.time()
            await mgr.broadcast("facility:1", {"type": "ping"})
            return loop.time() - started

        elapsed = asyncio.run(run_and_time())

        # Five stalled clients sequentially would be 5x the timeout.
        assert elapsed < 0.05 * 3
        assert healthy.received == [{"type": "ping"}]
        assert _channel_size(mgr, "facility:1") == 1


class TestHttpRequestIsUnaffected:
    def test_a_failing_subscriber_does_not_fail_the_write(self, client):
        """End to end, through the real handler: the record is committed and
        the broadcast fires with a subscriber that raises. The response must
        still be 201 — anything else invites a duplicate on retry.
        """
        organization = client.post(
            "/api/organizations",
            json={"name": "Broadcast Corp", "industry_type": "manufacturing"},
        ).json()
        facility = client.post(
            "/api/facilities",
            json={
                "organization_id": organization["id"],
                "name": "Broadcast Plant",
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

        channel = f"facility:{facility['id']}"
        bad = ExplodingSocket()
        manager.connect(channel, bad)
        try:
            response = client.post(
                "/api/consumption-records",
                json={
                    "emission_source_id": source["id"],
                    "facility_id": facility["id"],
                    "quantity_consumed": "1000",
                    "unit": "kWh",
                    "recorded_at": "2026-08-20T00:00:00Z",
                },
            )

            assert response.status_code == 201, response.text
            assert response.json()["facility_id"] == facility["id"]
            # And the dead subscriber was pruned along the way.
            assert bad not in manager._connections.get(channel, set())
        finally:
            manager.disconnect(channel, bad)

    def test_the_record_really_was_persisted(self, client):
        """Guards the other half of the duplicate-write scenario: the write
        must not be rolled back by broadcast trouble either."""
        organization = client.post(
            "/api/organizations",
            json={"name": "Persist Corp", "industry_type": "manufacturing"},
        ).json()
        facility = client.post(
            "/api/facilities",
            json={
                "organization_id": organization["id"],
                "name": "Persist Plant",
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

        channel = f"facility:{facility['id']}"
        manager.connect(channel, ExplodingSocket())
        try:
            client.post(
                "/api/consumption-records",
                json={
                    "emission_source_id": source["id"],
                    "facility_id": facility["id"],
                    "quantity_consumed": "1000",
                    "unit": "kWh",
                    "recorded_at": "2026-08-20T00:00:00Z",
                },
            )
            listed = client.get(
                f"/api/consumption-records?facility_id={facility['id']}"
            ).json()
            assert len(listed) == 1
        finally:
            manager._connections.pop(channel, None)
