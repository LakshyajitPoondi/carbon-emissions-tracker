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

## HTTPS (local dev)

The API also runs over TLS on port 8443, served directly by uvicorn. It is
**optional and additive** — plain HTTP on 8000 keeps working, which is what
the frontend dev server talks to.

One-time setup, per developer — generate a self-signed certificate:

```bash
# Git Bash / WSL / macOS
sh backend/scripts/generate-dev-cert.sh
```

```powershell
# Windows PowerShell
powershell -ExecutionPolicy Bypass -File backend\scripts\generate-dev-cert.ps1
```

No local `openssl`? The PowerShell script falls back to generating the
certificate inside the running backend container, or you can do that
directly:

```bash
docker compose exec backend sh /app/scripts/generate-dev-cert.sh
```

Either way the files land in `backend/certs/` (gitignored — **never commit
a private key**). Then start the HTTPS service:

```bash
docker compose --profile tls up -d backend-https
```

`https://localhost:8443/health` is now live. **Your browser will show a
security warning on first visit — that is expected, not a bug.** The
certificate is signed by nobody, so no browser trusts its issuer; click
through the warning ("Advanced" → "Proceed"). The certificate itself is
otherwise valid, including a `subjectAltName` covering `localhost`,
`127.0.0.1`, and the compose service names. With `curl`, either pass `-k`
to skip verification or trust the cert explicitly:

```bash
curl --cacert backend/certs/dev-cert.pem https://localhost:8443/health
```

In production, TLS is terminated by the hosting platform's managed
certificates and none of this applies. The app sends HSTS
(`Strict-Transport-Security`) on every response either way — see
`docs/api-contract.md`, "TLS / HTTPS".

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
