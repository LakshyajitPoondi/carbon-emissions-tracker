"""Shared test fixtures.

Connects to the Docker PostgreSQL on localhost:5432.
Each test runs inside a DB transaction that is rolled back afterward,
so tests never leave leftover data.
"""

import os

# Must be set before app.main is imported: the lifespan reads this at
# startup to decide whether to load the real YOLOv8n model. Without it,
# every test's TestClient(app) would load the real model from disk (via
# app.ml.load_model), adding real load latency to all 35+ existing tests
# that have nothing to do with Asset Scan. Tests that specifically exercise
# the asset-scan endpoint override app.ml.get_yolo_model with a fake instead
# (see test_asset_scan.py); the one test that verifies startup-loading
# itself unsets this for its own scope.
os.environ.setdefault("SKIP_MODEL_LOAD", "true")

# Same reasoning as SKIP_MODEL_LOAD: most tests have nothing to do with
# reports/WebSockets and shouldn't pay for (or require) a live Redis
# connection just to spin up a TestClient. The one test that verifies the
# Celery-worker-to-WebSocket bridge unsets this for its own scope.
os.environ.setdefault("SKIP_PUBSUB", "true")

# Same family of switch, for the ZPL label preview (app/services/labels.py),
# which normally POSTs the generated ZPL to Labelary to get a PNG back. The
# test suite must never make real network calls, and a default-on external
# call is the kind of thing a future test hits by accident: off by default
# here, so a test that wants the render path has to say so explicitly and
# mock httpx (see test_labels.py).
os.environ.setdefault("LABEL_PREVIEW_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.celery_app import celery_app
from app.database import get_db
from app.main import app

# Celery's eager mode: .delay()/.apply_async() run the task synchronously,
# in-process, instead of going through Redis to a real worker — exactly
# what the test suite needs (see docs/asset-scan-plan.md-style reasoning:
# tests shouldn't require a real running worker). task_eager_propagates
# makes an exception raised inside the task actually surface in the test
# instead of being silently swallowed.
celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)

# When running inside the Docker container (docker compose exec), the DB host
# is the service name "postgres".  DATABASE_URL is already set correctly in
# the container's environment via .env, so prefer that.
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    os.getenv(
        "DATABASE_URL",
        "postgresql://carbon_user:carbon_dev_pass_2026@postgres:5432/carbon_emissions",
    ),
)

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def db_session():
    """Yield a session wrapped in a transaction that is always rolled back."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def _celery_task_shares_test_transaction(db_session, monkeypatch):
    """app/tasks.py's Celery task opens its own SessionLocal() — correct
    and necessary for how it really runs in production (a separate worker
    process), but in eager-mode tests that would mean the task's session
    can't see the dispatching test's own data: each test's db_session lives
    inside a transaction that's rolled back at the end, never actually
    committed to the shared database, so a session on a different
    connection wouldn't see it. Bind a sessionmaker to the exact same
    connection as db_session so eager task execution sees the same
    in-progress transaction as the test that dispatched it."""
    test_sessionmaker = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)
    monkeypatch.setattr("app.tasks.SessionLocal", test_sessionmaker)


@pytest.fixture(autouse=True)
def _audit_middleware_shares_test_transaction(db_session, monkeypatch):
    """Same problem, same fix, for app/middleware/audit.py's background
    write. It deliberately opens its own SessionLocal() — an audit row must
    survive the rollback of the request it audits — but left alone in tests
    that means every audited request COMMITS a real row to the shared dev
    database, so the suite would both leak rows and be unable to see its
    own (the test's data lives in an uncommitted transaction on a different
    connection). Binding to db_session's connection puts the audit write
    inside the same transaction the test rolls back.

    Autouse rather than opt-in: any test that POSTs anything now produces
    audit rows, so every test needs this, not just the audit ones."""
    test_sessionmaker = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)
    monkeypatch.setattr("app.middleware.audit.SessionLocal", test_sessionmaker)


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient with the DB dependency overridden to use the
    rollback-scoped session from *db_session*.

    Every route except /auth/register and /auth/token now requires a bearer
    token, so this fixture registers+logs in a throwaway test user and sets
    the token as the client's default Authorization header. Existing tests
    that predate auth keep working unmodified; tests that specifically need
    to exercise unauthenticated/invalid-token behavior can override or clear
    the header themselves.
    """

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        register_resp = c.post(
            "/api/auth/register",
            json={"email": "fixture-user@example.com", "password": "fixture-pass-123"},
        )
        assert register_resp.status_code == 201, register_resp.text
        token_resp = c.post(
            "/api/auth/token",
            data={"username": "fixture-user@example.com", "password": "fixture-pass-123"},
        )
        assert token_resp.status_code == 200, token_resp.text
        c.headers["Authorization"] = f"Bearer {token_resp.json()['access_token']}"
        yield c
    app.dependency_overrides.clear()
