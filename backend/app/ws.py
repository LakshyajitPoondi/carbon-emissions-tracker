"""In-memory WebSocket connection manager for live dashboard/report updates.

A plain dict of channel -> set of active connections, scoped to a single
app instance/process. Channels are plain strings (e.g. "facility:5",
"organization:5") so unrelated broadcast scopes can share one manager
without key collisions.

Broadcasts triggered from within a FastAPI request (e.g.
consumption_records.py) can call manager.broadcast(...) directly — the
connections and the code doing the broadcasting are in the same process.
Broadcasts triggered from the Celery worker (a separate process) cannot
reach this manager directly; see app/pubsub.py for the Redis bridge that
makes that case work too.
"""

import asyncio
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# How long a single client gets to accept a broadcast before it is treated as
# dead. Short on purpose: a broadcast happens inline with an HTTP request that
# has already committed its database write, so the only thing waiting longer
# buys is a slower response for everyone else.
BROADCAST_SEND_TIMEOUT_SECONDS = 2.0


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}

    def connect(self, channel: str, websocket: WebSocket) -> None:
        self._connections.setdefault(channel, set()).add(websocket)

    def disconnect(self, channel: str, websocket: WebSocket) -> None:
        connections = self._connections.get(channel)
        if connections is None:
            return
        connections.discard(websocket)
        if not connections:
            self._connections.pop(channel, None)

    async def _send_one(self, websocket: WebSocket, message: dict) -> bool:
        """Deliver to one client. Returns False if it should be dropped.

        Swallows every Exception on purpose — see broadcast(). CancelledError
        derives from BaseException, so a genuine task cancellation still
        propagates rather than being mistaken for a dead client.
        """
        try:
            await asyncio.wait_for(
                websocket.send_json(message), timeout=BROADCAST_SEND_TIMEOUT_SECONDS
            )
            return True
        except asyncio.TimeoutError:
            logger.warning(
                "WebSocket send timed out after %ss; dropping the connection",
                BROADCAST_SEND_TIMEOUT_SECONDS,
            )
        except Exception:
            logger.warning("WebSocket send failed; dropping the connection", exc_info=True)
        return False

    async def broadcast(self, channel: str, message: dict) -> None:
        """Fan a message out to a channel. Never raises.

        Three properties this depends on, each one a bug that was here before:

        1. **It cannot fail its caller.** Broadcasts are triggered from HTTP
           handlers *after* their database write has committed. If a dead
           client could raise back into the handler, a successful write would
           be reported to the client as a 500 — and a client that retries a
           record it believes failed creates a duplicate. A broadcast is a
           courtesy; it must never rewrite the outcome of the request.

        2. **It iterates a snapshot.** A client disconnecting mid-broadcast
           mutates the live set, and iterating that set directly raises
           "Set changed size during iteration" — turning an ordinary
           disconnect into a failed request. The list() copy is taken before
           any await, so nothing can mutate it underneath us.

        3. **Every send is bounded and concurrent.** Sends run together with a
           per-client timeout, so one stalled connection delays neither the
           request nor the other subscribers, and the whole fan-out is bounded
           by the timeout rather than by the slowest client.

        Delivery is best-effort and in-memory. A client that is disconnected
        when the message goes out has simply missed it; there is no replay.
        """
        # Snapshot before the first await — see point 2 above.
        connections = list(self._connections.get(channel, ()))
        if not connections:
            return

        results = await asyncio.gather(
            *(self._send_one(websocket, message) for websocket in connections)
        )

        # A client that timed out or errored is removed, not merely skipped:
        # it would otherwise be retried on every future broadcast, paying the
        # full timeout each time.
        for websocket, delivered in zip(connections, results):
            if not delivered:
                self.disconnect(channel, websocket)


# Single process-wide instance — every module that needs to connect/broadcast
# imports this same object.
manager = ConnectionManager()
