FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required by: psycopg2-binary (gcc, libpq-dev);
# pyzbar (libzbar0 — pyzbar is a thin wrapper, it does not bundle the native
# zbar lib on Linux); opencv-python, which ultralytics hard-depends on and
# pip installs even when opencv-python-headless is also requested (libgl1,
# libglib2.0-0, libsm6, libxext6, libxrender1 — confirmed by an actual build:
# `import cv2` failed with "libGL.so.1: cannot open shared object file"
# without these); and curl (used below to fetch the YOLOv8n weights).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gcc libpq-dev libzbar0 curl \
       libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Bake the pretrained YOLOv8n weights into the image at build time — the
# demo can't depend on internet access being available when it's running.
# Pinned to an exact release asset rather than letting ultralytics resolve
# whatever its current default is.
RUN mkdir -p /app/models \
    && curl -L -o /app/models/yolov8n.pt \
       https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt

# Copy application code
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
