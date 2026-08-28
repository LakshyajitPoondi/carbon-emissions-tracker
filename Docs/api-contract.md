# API Contract — Carbon Emissions Tracking Platform (MVP)

This is the single source of truth for every frontend/backend interaction in the MVP.
Neither the Core Agent nor the Frontend Agent may change this file unilaterally.
Changes go through the "Contract Change Protocol" (see agents/core.md and agents/frontend.md).

Every endpoint below except `POST /auth/register` and `POST /auth/token` requires an `Authorization: Bearer <token>` header. Missing or invalid tokens return `401` using the Standard Error Shape.

Base URL (dev): `http://localhost:8000/api`

---

## Auth

### POST /auth/register
Request:
```json
{ "email": "user@example.com", "password": "hunter2!" }
```
Response `201`:
```json
{ "id": 1, "email": "user@example.com", "created_at": "2026-08-27T10:00:00Z" }
```
Errors: `422` if `email`/`password` missing or `email` already registered.

### POST /auth/token
OAuth2 password flow. Request is `application/x-www-form-urlencoded` (standard OAuth2PasswordRequestForm): `username` (the user's email) and `password`.

Response `200`:
```json
{ "access_token": "eyJhbGciOi...", "token_type": "bearer" }
```
Errors: `401` if credentials are invalid.

---

## Organizations

### POST /organizations
Create an organization.

Request:
```json
{ "name": "Acme Manufacturing", "industry_type": "manufacturing" }
```
Response `201`:
```json
{ "id": 1, "name": "Acme Manufacturing", "industry_type": "manufacturing", "created_at": "2026-08-26T10:00:00Z" }
```
Errors: `422` if `name` or `industry_type` missing/empty.

### GET /organizations/{id}
Response `200`: same shape as above. `404` if not found.

---

## Facilities

### POST /facilities
Request:
```json
{ "organization_id": 1, "name": "Chennai Plant", "location": "Chennai, TN", "facility_type": "factory" }
```
Response `201`: same fields + `id`, `created_at`, `updated_at`.
Errors: `404` if `organization_id` doesn't exist. `422` on missing fields.

### GET /facilities?organization_id={id}
Response `200`: array of facility objects.

---

## Emission Sources

### POST /emission-sources
Request:
```json
{ "facility_id": 1, "source_type": "ENERGY", "source_name": "Grid electricity", "unit_of_measurement": "kWh", "barcode_value": "ENSRC-00042" }
```
`source_type` must be one of: `ENERGY`, `FUEL`, `RESOURCE`. `barcode_value` is optional — omit or send `null` if the source has no barcode label yet.
Response `201`: object + `id`, timestamps, `barcode_value` (`null` if not set).
Errors: `404` if `facility_id` missing. `422` if `source_type` invalid, or `barcode_value` (when provided) already belongs to another source in the same facility (`BARCODE_ALREADY_ASSIGNED`).

### GET /emission-sources?facility_id={id}
Response `200`: array of emission source objects (each including `barcode_value`).

---

## Asset Scan

Merges the brief's barcode scanner + OpenCV + YOLO/Detectron2 requirements
into one feature: point a webcam at an emission source's barcode label, get
back the matching `emission_source`. See `docs/asset-scan-plan.md` for the
full design rationale, including why a pretrained YOLOv8n (no custom
training) is used only as an "is anything in frame" presence gate — it has
no "barcode" class, so pyzbar/zbar does the actual decode and localization.

### POST /facilities/{facility_id}/asset-scan
Request: `multipart/form-data` with a single `image` file field (JPEG or
PNG, ≤5MB) — a frame captured from the browser's webcam via
`canvas.toBlob()`.

Response `200` — barcode decoded and matched:
```json
{
  "decoded_value": "ENSRC-00042",
  "bounding_box": { "x": 118, "y": 76, "width": 240, "height": 118 },
  "emission_source": {
    "id": 7,
    "facility_id": 1,
    "source_type": "ENERGY",
    "source_name": "Grid electricity",
    "unit_of_measurement": "kWh",
    "barcode_value": "ENSRC-00042",
    "created_at": "2026-08-01T09:10:00Z",
    "updated_at": "2026-08-01T09:10:00Z"
  }
}
```
`bounding_box` is pixel coordinates in the submitted image, from the decoded
barcode's own symbol polygon. No `confidence` field — the decode is a
deterministic pass/fail, not a probabilistic score.

Errors:
- `404` if `facility_id` doesn't exist.
- `422 VALIDATION_ERROR` if `image` is missing, unreadable, or over 5MB.
- `422 NO_BARCODE_DETECTED` if no readable barcode was found in the frame at
  all (message varies slightly depending on whether the presence gate found
  *something* in frame that just wasn't a readable barcode, vs. nothing at
  all — the `code` is the same either way, only `message` differs).
- `422 BARCODE_NOT_MATCHED` if a barcode decoded successfully but no
  emission source in this facility carries that `barcode_value`.

---

## Emission Factors

Seeded via a migration/seed script, not created through the API in the MVP.

### GET /emission-factors?source_type={type}&region={region}
Response `200`:
```json
[
  {
    "id": 1,
    "source_type": "ENERGY",
    "region": "IN",
    "factor_value": "0.708200",
    "unit": "kg_co2e_per_kwh",
    "valid_from": "2026-01-01",
    "valid_to": null,
    "source_reference": "CEA 2025 grid emission factor"
  }
]
```

---

## Consumption Records (core input)

### POST /consumption-records
Creates a record AND synchronously computes + returns its emissions (no separate calculate step for MVP simplicity).

Request:
```json
{
  "emission_source_id": 3,
  "facility_id": 1,
  "quantity_consumed": "1250.500000",
  "unit": "kWh",
  "recorded_at": "2026-08-20T00:00:00Z"
}
```
Response `201`:
```json
{
  "id": 10,
  "emission_source_id": 3,
  "facility_id": 1,
  "quantity_consumed": "1250.500000",
  "unit": "kWh",
  "recorded_at": "2026-08-20T00:00:00Z",
  "created_at": "2026-08-26T10:05:00Z",
  "calculation": {
    "id": 7,
    "emission_factor_id": 1,
    "calculated_emissions_kg_co2e": "885.679730",
    "calculation_date": "2026-08-26"
  }
}
```
Errors: `404` if `emission_source_id`/`facility_id` invalid. `422` if no matching emission factor exists for that source's region/type (report this as a specific error code `NO_MATCHING_FACTOR` so the frontend can show a clear message, not a generic 500).

### GET /consumption-records?facility_id={id}&start_date=&end_date=
Response `200`: array of consumption records, each including its nested `calculation` object (or `null` if none).

---

## Emissions Summary (dashboard)

### GET /facilities/{id}/emissions-summary?start_date=&end_date=
Response `200`:
```json
{
  "facility_id": 1,
  "period": { "start": "2026-08-01", "end": "2026-08-26" },
  "total_emissions_kg_co2e": "12045.30",
  "by_source_type": {
    "ENERGY": "8000.10",
    "FUEL": "3500.20",
    "RESOURCE": "545.00"
  }
}
```

---

## Reports

Generation is asynchronous (Celery + Redis) — `POST /reports/generate`
returns immediately with the report in `pending` status; the actual
aggregation happens in a background worker. Poll `GET /reports/{id}`, or
connect to the WebSocket channel below to be pushed the finished report
instead of polling.

`status` is one of `draft` (unused, predates this flow) · `pending` (row
created, generation not started yet) · `processing` (worker is aggregating)
· `final` (done — `total_emissions_kg_co2e` and `facilities` are populated).
`total_emissions_kg_co2e` and `facilities` are `null` until `final` — a
report's totals are computed exactly once and stored, not recomputed on
every read, so a `final` report's numbers are a stable snapshot of when it
was generated.

### POST /reports/generate
Request:
```json
{ "organization_id": 1, "report_period_start": "2026-08-01", "report_period_end": "2026-08-26" }
```
Response `201` — always `pending`, immediately, regardless of how fast the
worker actually finishes:
```json
{
  "id": 4,
  "organization_id": 1,
  "report_period_start": "2026-08-01",
  "report_period_end": "2026-08-26",
  "generated_at": "2026-08-26T10:10:00Z",
  "status": "pending",
  "total_emissions_kg_co2e": null,
  "facilities": null
}
```
Errors: `404` if `organization_id` doesn't exist.

### GET /reports/{id}
Same shape, whatever the report's current status is. `total_emissions_kg_co2e`/
`facilities` are `null` for `pending`/`processing`, populated for `final`.
`404` if not found.

### GET /reports?organization_id={id}
Response `200`: array of report summaries (without the nested `facilities`
breakdown — that's only on the detail view; `total_emissions_kg_co2e` is
still `null` for non-`final` reports in the list too).

---

## WebSocket

Two channels, both push-only (clients aren't expected to send anything
after connecting) and both under the same `/ws` prefix — not under `/api`
(matches `/health`'s pattern of sitting outside the versioned REST
namespace). Both take `token` as a query param — the same JWT every other
endpoint takes as `Authorization: Bearer`, but a browser `WebSocket`
handshake can't carry custom headers the way `fetch` can.

**Auth/rejection** (both channels): the connection is validated *before*
being accepted — an unauthenticated or not-found connection is never
silently accepted and then dropped. Close codes:
- `1008` (Policy Violation — the standard RFC 6455 code closest to "missing
  or invalid credentials") if `token` is missing, malformed, or doesn't
  resolve to a user.
- `4004` (private-use range, mirrors HTTP `404`) if the resource (facility
  or organization) doesn't exist.

### GET /ws/facilities/{facility_id}?token={jwt}

A client connects once per facility it's viewing and is pushed a message
whenever a new consumption record is created for that facility, instead of
polling.

**Message sent on `POST /consumption-records` success**, to every client
connected to that record's `facility_id`:
```json
{
  "type": "consumption_record_created",
  "consumption_record": {
    "id": 10,
    "emission_source_id": 3,
    "facility_id": 1,
    "quantity_consumed": "1250.500000",
    "unit": "kWh",
    "recorded_at": "2026-08-20T00:00:00Z",
    "created_at": "2026-08-26T10:05:00Z",
    "calculation": {
      "id": 7,
      "emission_factor_id": 1,
      "calculated_emissions_kg_co2e": "885.679730",
      "calculation_date": "2026-08-26"
    }
  }
}
```
Same shape as a `POST /consumption-records` response — not a pre-aggregated
`by_source_type` total. The server has no way to know which date range each
connected dashboard currently has selected (`GET
/facilities/{id}/emissions-summary?start_date=&end_date=` is client-driven),
so it can't correctly compute "the new total" on a client's behalf without
risking sending a number that doesn't match what that client is actually
looking at. Sending the raw record instead lets the frontend decide: refetch
the summary outright, or bump a locally-held total only if this record's
`recorded_at` falls inside the period currently being viewed.

### GET /ws/organizations/{organization_id}?token={jwt}

A client connects once per organization it's viewing reports for, and is
pushed a message when an async report generation task finishes — so the
Reports screen can know a report is ready without polling `GET
/reports/{id}`.

Note this is a genuinely different process than the facility channel: report
generation runs in the `celery-worker` container, a separate process from
the one holding the WebSocket connection open, so the finished-report
message can't be delivered by a direct in-process call the way the
consumption-record broadcast is. It's relayed through Redis pub/sub — the
worker publishes, the web process re-broadcasts to its own connected
clients. Not observable from the API surface; noted here only so it's clear
this channel depends on Redis being reachable from both containers, not
just Celery's queue.

**Message sent when a report reaches `final`**, to every client connected to
that report's `organization_id`:
```json
{
  "type": "report_generated",
  "report": {
    "id": 4,
    "organization_id": 1,
    "report_period_start": "2026-08-01",
    "report_period_end": "2026-08-26",
    "generated_at": "2026-08-26T10:10:00Z",
    "status": "final",
    "total_emissions_kg_co2e": "12045.30",
    "facilities": [
      { "facility_id": 1, "facility_name": "Chennai Plant", "total_emissions_kg_co2e": "12045.30" }
    ]
  }
}
```
Same shape as the `GET /reports/{id}` response, sent in full — unlike the
consumption-record broadcast, there's no "which period is currently
selected" ambiguity here (a report's period is fixed at generation time), so
there's no reason to hold anything back or make the frontend re-fetch.

Clients aren't expected to send anything after connecting on either
channel — both are server-push-only.

---

## GraphQL

A read-only query layer alongside the REST API above — REST remains the
source of truth for every create/update; there is no GraphQL mutation type
at all. This exists for clients that want one round trip for an
organization's facilities and their emissions summaries together, instead
of `GET /organizations/{id}` + `GET /facilities?organization_id=` +
one `GET /facilities/{id}/emissions-summary` per facility.

### POST /graphql

Same auth as every REST endpoint: `Authorization: Bearer <token>` is
required, enforced before the query executes — a missing or invalid token
gets the same `401` + Standard Error Shape response as any REST endpoint,
not a GraphQL-shaped error. Like `/health` and `/ws`, this sits outside the
`/api` prefix.

Standard GraphQL-over-HTTP request/response: POST a JSON body
`{ "query": "...", "variables": {...} }`, get back `{ "data": ..., "errors": [...] }`
(`errors` omitted when there are none). A resolver-level failure (e.g. a
nonexistent organization, below) is carried in `errors`, not the HTTP status
— the transport-level response is still `200`.

Field names are camelCase (`industryType`, `emissionsSummary`,
`totalEmissionsKgCo2e`), following standard GraphQL convention, even though
the equivalent REST fields are snake_case.

### Schema

```graphql
type Query {
  organization(id: Int!): Organization
}

type Organization {
  id: Int!
  name: String!
  industryType: String!
  createdAt: DateTime!
  facilities: [Facility!]!
}

type Facility {
  id: Int!
  organizationId: Int!
  name: String!
  location: String!
  facilityType: String!
  createdAt: DateTime!
  updatedAt: DateTime!
  emissionsSummary(startDate: Date!, endDate: Date!): EmissionsSummary!
  emissionSources: [EmissionSource!]!
}

type EmissionsSummary {
  facilityId: Int!
  periodStart: Date!
  periodEnd: Date!
  totalEmissionsKgCo2e: Decimal!
  bySourceType: JSON!   # e.g. { "ENERGY": "8000.10", "FUEL": "3500.20", "RESOURCE": "545.00" }
}

type EmissionSource {
  id: Int!
  facilityId: Int!
  sourceType: SourceType!   # enum: ENERGY | FUEL | RESOURCE
  sourceName: String!
  unitOfMeasurement: String!
  barcodeValue: String
  createdAt: DateTime!
  updatedAt: DateTime!
}
```

`Decimal` serializes as a string, same convention as REST's decimal fields
(`"12045.30"`, not a raw JSON number) — precision matters here, so it's
never passed through a float. `emissionsSummary` computes the same way
`GET /facilities/{id}/emissions-summary` does and returns identical
numbers for the same facility/period; `emissionSources` returns the same
rows as `GET /emission-sources?facility_id={id}`.

### Example

Request:
```json
{
  "query": "query Q($orgId: Int!, $start: Date!, $end: Date!) { organization(id: $orgId) { id name industryType facilities { id name emissionsSummary(startDate: $start, endDate: $end) { totalEmissionsKgCo2e bySourceType } } } }",
  "variables": { "orgId": 1, "start": "2026-08-01", "end": "2026-08-26" }
}
```

Response `200`:
```json
{
  "data": {
    "organization": {
      "id": 1,
      "name": "Acme Manufacturing",
      "industryType": "manufacturing",
      "facilities": [
        {
          "id": 1,
          "name": "Chennai Plant",
          "emissionsSummary": {
            "totalEmissionsKgCo2e": "12045.30",
            "bySourceType": { "ENERGY": "8000.10", "FUEL": "3500.20", "RESOURCE": "545.00" }
          }
        }
      ]
    }
  }
}
```

Nonexistent organization — `data.organization` is `null`, the reason is in
`errors`, not an HTTP `404`:
```json
{
  "data": { "organization": null },
  "errors": [
    {
      "message": "Organization 999 does not exist",
      "path": ["organization"],
      "extensions": { "code": "NOT_FOUND" }
    }
  ]
}
```

### N+1 note

Naively resolving `emissionsSummary` (or `emissionSources`) once per
facility under one `organization(id)` query would fire one query per
facility for each field (20 facilities → 20 queries, per field). Both
fields are batched per query execution instead — `emissionsSummary` calls
are grouped by `(startDate, endDate)`, the normal case where every facility
in the request shares the same period, into one grouped SQL query per
distinct period; `emissionSources` calls are batched into a single
`facility_id IN (...)` query. Either way, the common case costs exactly one
query per field regardless of facility count, not one per facility.

---

## Standard Error Shape

All errors follow:
```json
{ "error": { "code": "NOT_FOUND", "message": "Facility 99 does not exist" } }
```
Frontend should branch UI behavior on `error.code`, not on parsing `message` text.

## Status Codes Used
`200` OK · `201` Created · `404` Not Found · `422` Validation Error · `500` Unexpected server error (should be rare — Core Agent should turn known failure cases into 404/422 with a clear `code`, not let them fall through to 500)
