# carbon-emissions-tracker
Track energy, fuel, and resource consumption to calculate carbon emissions and generate sustainability reports. FastAPI + PostgreSQL backend, React dashboard.
# Carbon Emissions Tracking Platform

Track energy, fuel, and resource consumption across facilities to calculate
carbon emissions and generate sustainability reports.

## Stack

- **Backend:** FastAPI, SQLAlchemy, Alembic, PostgreSQL
- **Frontend:** React + TypeScript
- **Infra:** Docker Compose

## Scope

The full stack from the original brief is implemented — this is not a
reduced MVP. Shipped and working:

- **Core domain** — organizations, facilities, and emission sources
  (energy/fuel/resource), with consumption tracking and deterministic
  `Decimal` emissions calculation against seeded emission factors
- **Summaries and reports** — per-facility emissions dashboards and
  organization-wide sustainability reports
- **Authentication** — OAuth2 password flow issuing JWT bearer tokens;
  every endpoint protected
- **Asset Scan** — barcode capture from a browser webcam, decoded with
  OpenCV + pyzbar, with a pretrained YOLOv8n model as a presence gate
  (see [`docs/asset-scan-plan.md`](docs/asset-scan-plan.md))
- **WebSocket live updates** — facility and organization channels pushing
  new consumption records and report completion straight to the dashboard
- **Celery async reports** — report generation off the request path via a
  Redis broker and a dedicated worker, bridged back to WebSocket clients
  with Redis pub/sub
- **GraphQL** — read-only query layer at `/graphql` alongside REST, with
  DataLoader batching (see [GraphQL](#graphql) below)
- **Audit logging** — every write request recorded and queryable at
  `/api/audit-logs`
- **ZPL label generation** — printer-ready Code 128 asset labels with an
  optional rendered preview
- **TLS/HSTS** — HTTPS in local development served by uvicorn, plus
  security headers on every response

### Out of scope: RFID and physical hardware

No RFID reader, handheld barcode scanner, or Zebra label printer was
available for this project, so nothing that depends on that hardware is
implemented. Stated plainly rather than stubbed out to look complete:

- **RFID integration is cut entirely.** There is no reader, so there is no
  RFID code.
- **Barcode scanning** runs through a laptop webcam in the browser rather
  than a dedicated scanner gun. The decode is real; the input device is
  not the one the brief imagined.
- **ZPL labels** are generated as valid, printer-ready ZPL text plus a
  rendered preview image. Nothing is ever sent to a physical printer.

### Still in progress

- Kubernetes manifests and an actual deploy to Docker Desktop's built-in
  single-node cluster
- GitHub Actions CI (backend test job, frontend build job)

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


## GraphQL

The read-only GraphQL layer is demoed through the **built-in GraphiQL
console at `/graphql`**, not through a dedicated frontend screen. That is a
deliberate scope decision rather than an unfinished feature: REST remains
the only write path, and the React dashboard already covers every read the
UI needs, so a second frontend data path would duplicate working screens
without showing anything GraphQL-specific. Nested queries, the schema
browser, and the batched DataLoader resolvers are all far more visible in
GraphiQL than they would be behind a chart that looks identical either way.

One wrinkle worth knowing before demoing it: `/graphql` is protected by the
same JWT auth as every other endpoint, and that includes the `GET` request
that serves the GraphiQL page itself. Navigating a browser straight to
`http://localhost:8000/graphql` therefore returns `401` — an address bar
cannot send an `Authorization` header. Two ways round it:

**Use the console** — inject the header with a browser extension such as
ModHeader, then load the page:

```
Authorization: Bearer <token from POST /api/auth/token>
```

**Or query the endpoint directly**, no console needed:

```bash
curl -X POST http://localhost:8000/graphql \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"{ organization(id: 1) { name industryType facilities { id name } } }"}'
```

```json
{"data":{"organization":{"name":"Acme Manufacturing","industryType":"manufacturing","facilities":[]}}}
```

See [`docs/api-contract.md`](docs/api-contract.md), "GraphQL", for the full
schema, the camelCase field convention, and how the N+1 batching works.

## API Contract

See [`docs/api-contract.md`](docs/api-contract.md) for the full endpoint
reference — request/response shapes, error codes, and status codes.
