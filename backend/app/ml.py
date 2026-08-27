"""YOLOv8n model loading for the Asset Scan feature.

Loaded exactly once, at application startup, via the lifespan handler in
app.main — never per-request. Routes access the already-loaded singleton
through get_yolo_model, a FastAPI dependency, so tests can override it with a
fake instead of paying real model-load cost on every test.
"""

import os

from fastapi import Request
from ultralytics import YOLO

MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "/app/models/yolov8n.pt")


def load_model():
    """Called once from app.main's lifespan. Returns None when
    SKIP_MODEL_LOAD=true (set by the test suite) so tests never pay real
    model-load cost just by spinning up a TestClient — asset-scan tests that
    need a model override get_yolo_model with a fake instead."""
    if os.getenv("SKIP_MODEL_LOAD") == "true":
        return None
    return YOLO(MODEL_PATH)


def get_yolo_model(request: Request):
    return request.app.state.yolo_model
