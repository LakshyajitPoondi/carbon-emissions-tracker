"""Shared test fixtures.

Connects to the Docker PostgreSQL on localhost:5432.
Each test runs inside a DB transaction that is rolled back afterward,
so tests never leave leftover data.
"""

import os

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
    rollback-scoped session from *db_session*."""

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
