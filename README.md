# carbon-emissions-tracker
Track energy, fuel, and resource consumption to calculate carbon emissions and generate sustainability reports. FastAPI + PostgreSQL backend, React dashboard.
# Carbon Emissions Tracking Platform

Track energy, fuel, and resource consumption across facilities to calculate
carbon emissions and generate sustainability reports.

## Stack

- **Backend:** FastAPI, SQLAlchemy, Alembic, PostgreSQL
- **Frontend:** React + TypeScript
- **Infra:** Docker Compose

## MVP Scope

This is a college-project MVP, deliberately scoped down from a larger brief.
Included:

- Organizations, facilities, and emission sources (energy/fuel/resource)
- Consumption tracking with automatic emissions calculation
- Emissions summary dashboards
- Sustainability report generation

Explicitly **not** in this MVP (see `docs/api-contract.md` for the frozen API
surface): authentication, computer vision, RFID/barcode hardware integration,
Kubernetes, Celery, WebSockets, GraphQL.

## Running locally

```bash
docker compose up --build -d
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seed
```

API available at `http://localhost:8000`. Health check: `GET /health`.

## Testing

```bash
docker compose exec backend pytest tests/ -v
```

## Project structure
backend/
app/
models/ # SQLAlchemy models
schemas/ # Pydantic request/response schemas
routers/ # API endpoints
services/ # Business logic (emissions calculation, report aggregation)
alembic/ # Database migrations
tests/
frontend/ # React + TypeScript dashboard
docs/
api-contract.md # Frozen API contract — source of truth for backend/frontend
agents/
core.md # Backend agent operating rules
frontend.md # Frontend agent operating rules


## API Contract

See [`docs/api-contract.md`](docs/api-contract.md) for the full endpoint
reference — request/response shapes, error codes, and status codes.
