"""In-memory WebSocket connection manager for live facility dashboard updates.

A plain dict of facility_id -> set of active connections, scoped to a single
app instance/process — correct for this project's single-container
deployment. This would need a shared pub/sub layer (e.g. Redis) to fan
broadcasts out across multiple backend instances/replicas; that's out of
scope here.
"""

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = {}

    def connect(self, facility_id: int, websocket: WebSocket) -> None:
        self._connections.setdefault(facility_id, set()).add(websocket)

    def disconnect(self, facility_id: int, websocket: WebSocket) -> None:
        connections = self._connections.get(facility_id)
        if connections is None:
            return
        connections.discard(websocket)
        if not connections:
            self._connections.pop(facility_id, None)

    async def broadcast(self, facility_id: int, message: dict) -> None:
        connections = self._connections.get(facility_id)
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
            self.disconnect(facility_id, websocket)


# Single process-wide instance — every module that needs to connect/broadcast
# imports this same object.
manager = ConnectionManager()
