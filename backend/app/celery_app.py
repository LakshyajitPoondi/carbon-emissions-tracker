"""Celery application — broker and result backend are both Redis (no custom
config needed at this scale, per the task).

Deliberately does NOT import app.main: this module is imported by both the
FastAPI process (to dispatch tasks via .delay()) and the celery-worker
process (to execute them). The worker has no business loading the FastAPI
app object, its CORS middleware, or the YOLOv8n model — none of that is
relevant to running a task, and loading the model would waste the worker's
startup time for nothing.
"""

import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "carbon_emissions",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)
