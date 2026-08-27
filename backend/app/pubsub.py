"""Redis pub/sub bridge for cross-process WebSocket broadcasts.

The in-process ConnectionManager (app/ws.py) only knows about WebSocket
connections held open by THIS process. That's fine for broadcasts triggered
from within a FastAPI request (e.g. consumption_records.py — same process
as the connections) but not for the Celery worker, which runs in a
completely separate process with its own memory space: it has no way to
reach a WebSocket the web server is holding open, no matter how directly it
calls manager.broadcast(...).

The fix: the worker PUBLISHes a message on a Redis channel; the FastAPI
process SUBSCRIBEs to that channel for its whole lifetime (started in
app.main's lifespan) and re-broadcasts anything it receives onto its own
real, in-process ConnectionManager. Publishing is synchronous (used from the
sync Celery task); subscribing is asynchronous (runs as a background task
alongside the FastAPI event loop).
"""

import json
import os

import redis
import redis.asyncio as aredis

from app.ws import manager

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
PUBSUB_CHANNEL = "ws:broadcast"


def publish_ws_message(channel: str, message: dict) -> None:
    """Sync publish — used from the Celery worker process."""
    client = redis.Redis.from_url(REDIS_URL)
    try:
        client.publish(PUBSUB_CHANNEL, json.dumps({"channel": channel, "message": message}))
    finally:
        client.close()


async def run_subscriber() -> None:
    """Runs for the lifetime of the FastAPI process (started as a background
    task in app.main's lifespan). Re-broadcasts anything published on
    PUBSUB_CHANNEL onto the real in-process ConnectionManager."""
    client = aredis.from_url(REDIS_URL)
    pubsub = client.pubsub()
    await pubsub.subscribe(PUBSUB_CHANNEL)
    try:
        async for raw in pubsub.listen():
            if raw["type"] != "message":
                continue
            try:
                envelope = json.loads(raw["data"])
                await manager.broadcast(envelope["channel"], envelope["message"])
            except Exception:
                # A malformed envelope must never kill the subscriber loop —
                # that would silently stop ALL future live updates for the
                # rest of the process's life. (Deliberately narrower than
                # the `async for` itself, so asyncio.CancelledError from
                # lifespan shutdown still propagates normally.)
                continue
    finally:
        await pubsub.unsubscribe(PUBSUB_CHANNEL)
        await client.aclose()
