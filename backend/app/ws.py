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

from fastapi import WebSocket


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

    async def broadcast(self, channel: str, message: dict) -> None:
        connections = self._connections.get(channel)
        if not connections:
            return
        # A send can fail if a client dropped without a clean close frame
        # reaching us yet — prune those rather than letting one dead
        # connection break the broadcast for everyone else.
        stale: set[WebSocket] = set()
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception:
                stale.add(websocket)
        for websocket in stale:
            self.disconnect(channel, websocket)


# Single process-wide instance — every module that needs to connect/broadcast
# imports this same object.
manager = ConnectionManager()
