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

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import get_db
from app.main import app

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
