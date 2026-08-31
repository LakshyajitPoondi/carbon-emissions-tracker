# API Contract — Carbon Emissions Tracking Platform (MVP)

This is the single source of truth for every frontend/backend interaction in the MVP.
Neither the Core Agent nor the Frontend Agent may change this file unilaterally.
Changes go through the "Contract Change Protocol" (see agents/core.md and agents/frontend.md).

Every endpoint below except `POST /auth/register` and `POST /auth/token` requires an `Authorization: Bearer <token>` header. Missing or invalid tokens return `401` using the Standard Error Shape.

Base URL (dev): `http://localhost:8000/api` — or
`https://localhost:8443/api` over TLS; see "TLS / HTTPS" below.

---

## TLS / HTTPS

The API is reachable over both plain HTTP and TLS in local development:

| | Base URL | WebSocket | Notes |
| --- | --- | --- | --- |
| Plain HTTP | `http://localhost:8000/api` | `ws://localhost:8000/ws/...` | Always on. What the frontend dev server talks to. |
| TLS | `https://localhost:8443/api` | `wss://localhost:8443/ws/...` | Optional; start with `docker compose --profile tls up -d backend-https`. |

Both are the same application serving the same contract — every endpoint,
error shape, and WebSocket channel documented here behaves identically on
either. TLS is terminated by uvicorn itself (`--ssl-keyfile` /
`--ssl-certfile`), not by a separate reverse proxy.

**The local certificate is self-signed, so browsers will show a security
warning on first visit. That is expected and documented behaviour, not a
bug.** The certificate is signed by no recognised authority, so no browser
trusts its issuer; click through the warning to proceed. It is otherwise a
well-formed certificate — `subjectAltName` covers `localhost`,
`127.0.0.1`, `::1`, and the compose service names, so hostname validation
passes and a client that is told to trust the cert accepts it outright:

```bash
curl --cacert backend/certs/dev-cert.pem https://localhost:8443/health   # verifies cleanly
```

Generating the certificate is a one-time per-developer step
(`backend/scripts/generate-dev-cert.sh` or `.ps1`) — see the README,
"HTTPS (local dev)". The certificate and key are gitignored and never
committed.

**In production**, TLS is terminated by the hosting platform's managed
certificates (Render for the backend, Vercel for the frontend). The
application does not terminate TLS there and needs no certificate of its
own; the self-signed dev certificate is strictly a local-development
convenience.

### Security headers

Every response — successful or not, on both HTTP and HTTPS — carries:

| Header | Value | Purpose |
| --- | --- | --- |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | Tells the browser never to speak plain HTTP to this origin again. |
| `X-Content-Type-Options` | `nosniff` | Stops MIME-sniffing a response into something executable. |
| `X-Frame-Options` | `DENY` | Nothing here is meant to be framed. |
| `Referrer-Policy` | `no-referrer` | API URLs carry record ids; don't leak them to third parties. |

HSTS is sent **unconditionally, including over plain HTTP**. That is
deliberate: RFC 6797 requires browsers to ignore the header when it arrives
over an insecure transport, so sending it on HTTP is inert rather than
harmful — while the alternative, sending it only when the request looks
secure, would suppress it in exactly the deployment that needs it most. In
production the platform terminates TLS upstream and the application only
ever sees plain HTTP from the proxy, so a scheme-conditional header would
never be sent at all. A hosting platform providing HTTPS is not the same
thing as the app telling browsers to *insist* on HTTPS; this header is that
second part.

Configurable via the environment (see `.env.example`): `HSTS_ENABLED`,
`HSTS_MAX_AGE`, `HSTS_INCLUDE_SUBDOMAINS`, `HSTS_PRELOAD`. `preload` is off
by default — submitting an origin to the browser preload list is
effectively irreversible on any useful timescale.

There is deliberately **no** `Content-Security-Policy`: this app serves
Swagger UI at `/docs` and GraphiQL at `/graphql`, both of which load
scripts and styles from a CDN, and a blanket CSP would silently break both
interactive consoles.

---

## Authorization and organization membership

Authentication answers *who is this*; membership answers *is this theirs*.
A valid token alone grants access to nothing.

Users are linked to organizations through `organization_members`
(`user_id`, `organization_id`, `role`). Valid roles are `OWNER`, `ADMIN`, and
`EMPLOYEE`; a database CHECK constraint rejects every other value.

- `OWNER` and `ADMIN` have identical full access to every existing action in
  the organization.
- `EMPLOYEE` may use every read-only REST endpoint, GraphQL query, WebSocket
  channel, and the read-only asset scan. It may also create consumption
  records as an append-only entry action.
- `EMPLOYEE` may not perform other mutations, including creating facilities
  or emission sources and generating reports. A role denial uses the same
  masked `404 NOT_FOUND` response as a missing resource or non-membership.

Roles are scoped to one organization. Any authenticated user may create a
new organization and becomes its `OWNER`, regardless of their role in other
organizations.

**How membership is created.** `POST /organizations` makes the calling user
an `OWNER` of the organization it creates, in the same transaction. That is
the *only* way a membership comes into existence in this version. In
particular:

- Registering an account grants no membership. A new user belongs to nothing
  and sees nothing until they create an organization.
- There is no endpoint for adding another user to an existing organization
  yet. The schema supports it; the API deliberately does not expose it.

**What membership gates.** Every organization-owned resource, reached either
directly (`organizations`, `reports`) or by walking foreign keys
(`emission_sources` → `facilities` → organization). This applies identically
across REST, GraphQL and WebSockets — there is no path to the data that
skips the check.

The one deliberate exception is `GET /emission-factors`: published emission
coefficients are shared reference data with no `organization_id` and no
per-tenant meaning. It requires a token but not a membership. This is a
decision, not an omission.

**Denials are indistinguishable from absence.** A resource belonging to
another organization returns exactly what a nonexistent one returns — `404`
with code `NOT_FOUND` and the same message wording. See "Standard Error
Shape" for why `404` rather than `403`.

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
{ "id": 1, "name": "Acme Manufacturing", "industry_type": "manufacturing", "created_at": "2026-08-26T10:00:00Z", "role": "OWNER" }
```
Errors: `422` if `name` or `industry_type` missing/empty.

The caller becomes an `OWNER` member of the organization it creates — see
"Authorization and organization membership".

### GET /organizations
List the organizations the authenticated user is a **member of**. This is the
endpoint a client uses to populate an organization picker; there is no way to
enumerate organizations you do not belong to.

Response `200`: array of organization objects, same shape as
`GET /organizations/{id}`:
```json
[
  { "id": 1, "name": "Acme Manufacturing", "industry_type": "manufacturing", "created_at": "2026-08-26T10:00:00Z", "role": "OWNER" },
  { "id": 4, "name": "Zephyr Logistics", "industry_type": "logistics", "created_at": "2026-08-27T09:00:00Z", "role": "EMPLOYEE" }
]
```

Returns `[]` — not a `404` — for a user with no memberships. A newly
registered account is exactly this case, and clients should treat it as a
first-run empty state rather than an error.

**Ordering** is by `name` ascending, with `id` ascending as a tie-break so
that organizations sharing a name still come back in a stable order. The
order is guaranteed to be the same across calls for the same data.

**No pagination.** The result is bounded by how many organizations one person
has been added to — single digits in practice. Since the ordering is stable,
pagination can be introduced later without changing the results callers
already see.

Errors: `401` without a valid bearer token, as everywhere.

### GET /organizations/{id}
Response `200`: same shape as above. `404` if it does not exist **or you are
not a member of it** — the two are indistinguishable by design.

For every organization response, `role` is the authenticated caller's role
in that organization, not a property of the organization itself.

---

## Facilities

### POST /facilities
Request:
```json
{ "organization_id": 1, "name": "Chennai Plant", "location": "Chennai, TN", "facility_type": "factory" }
```
Response `201`: same fields + `id`, `created_at`, `updated_at`.
Errors: `404` if `organization_id` doesn't exist or you are not a member of
it. `422` on missing fields.

### GET /facilities?organization_id={id}
Response `200`: array of facility objects. `404` if the organization does not
exist or you are not a member — deliberately not an empty `200`, which would
still confirm the id is real.

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

## Labels (ZPL)

The counterpart to Asset Scan: that feature *reads* a barcode off a label,
this one *generates* the label to stick on the equipment in the first place.

There is no physical Zebra printer in this project, so the deliverable is
valid printer-ready **ZPL II text** the user can copy or download and send
to a real printer later — not an actual print job. An optional rendered PNG
preview is included so the label can be seen without one.

The label is 4" x 2" at 8 dots/mm (203 dpi) — 812 x 406 dots — and carries
the source name, its facility name, `source_type / unit_of_measurement`,
and `barcode_value` encoded as **Code 128** (`^BC`) with the
human-readable interpretation line printed beneath the bars. Nothing is
stored: the label is regenerated on each request, so it always reflects the
source's current name and barcode.

### GET /emission-sources/{id}/label

Query parameters:

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `preview` | bool | `true` | Render a PNG preview. `false` skips the outbound call to the external renderer and returns ZPL text only. |

Response `200`:
```json
{
  "emission_source_id": 7,
  "barcode_value": "ENSRC-00042",
  "zpl_code": "^XA\n^CI28\n^PW812\n^LL406\n^LH0,0\n^FO30,28^A0N,40,40^FH_^FDGrid electricity^FS\n^FO30,84^A0N,28,28^FH_^FDChennai Plant^FS\n^FO30,122^A0N,28,28^FH_^FDENERGY / kWh^FS\n^BY3,3,100\n^FO30,170^BCN,100,Y,N,N^FH_^FDENSRC-00042^FS\n^XZ\n",
  "label_width_inches": 4.0,
  "label_height_inches": 2.0,
  "print_density_dpmm": 8,
  "preview_png_base64": "iVBORw0KGgoAAAANSUhEUg...",
  "preview_note": null
}
```

`preview_png_base64` is a base64-encoded PNG, ready to drop into an
`<img src="data:image/png;base64,...">`. It is `null` whenever no preview
was produced, and `preview_note` then explains why — `zpl_code` is
identical either way.

**Preview rendering.** The PNG comes from [Labelary](https://labelary.com),
a free public ZPL-to-image API. It is optional decoration: if the service
is unreachable, times out, or returns an error, the endpoint still returns
`200` with the full ZPL and a `preview_note` saying the preview was
unavailable — an optional cosmetic feature never fails the request. Two
things worth knowing: using it sends the label's contents (source name,
facility name, barcode) to a third party, and it adds one outbound HTTP
call to the request. Either reason is grounds to pass `preview=false`, or
to set `LABEL_PREVIEW_ENABLED=false` to turn it off service-wide.

**Text handling.** `^` and `~` are ZPL control characters; any occurrence
in a source or facility name is emitted as a `^FH_` hex escape so label
text can never be interpreted as a command. Text longer than the label is
trimmed with a trailing `...` rather than silently clipped at the label
edge.

Errors:

| Status | Code | When |
| --- | --- | --- |
| `404` | `NOT_FOUND` | No emission source with that id. |
| `422` | `BARCODE_NOT_ASSIGNED` | The source has no `barcode_value`. A label with an empty barcode looks scannable and then fails at the scanner, so it is refused: assign a barcode to the source first. |
| `401` | `UNAUTHORIZED` | Missing or invalid bearer token, as everywhere. |

```json
{
  "error": {
    "code": "BARCODE_NOT_ASSIGNED",
    "message": "Emission source 7 has no barcode_value, so no barcode can be encoded on its label. Assign a barcode to the source first, then request the label again."
  }
}
```

---

## Emission Factors

Seeded via a migration/seed script, not created through the API in the MVP.

**Not membership-scoped, deliberately.** These are published coefficients shared by every organization — reference data with no `organization_id`. A valid token is required; a membership is not. See "Authorization and organization membership".

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
Errors: `404` if `emission_source_id`/`facility_id` is invalid **or belongs to another organization**. `422` `SOURCE_FACILITY_MISMATCH` if the source exists and is accessible but belongs to a different facility than the one the record is filed against — enforced by a composite foreign key in the database as well as by the handler, so no write path can bypass it. `422` if no matching emission factor exists for that source's region/type (report this as a specific error code `NO_MATCHING_FACTOR` so the frontend can show a clear message, not a generic 500).

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
  or organization) doesn't exist, **or you are not a member of its
  organization**. Deliberately the same code for both: a distinct
  "forbidden" code would let anyone enumerate valid facility ids over the
  socket, undoing the `404` masking the REST layer performs. Membership is
  checked before `accept()`, so a non-member never joins the channel.

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

**Membership is enforced identically to REST.** `organization(id)` resolves
only organizations you belong to; anything else returns `data.organization:
null` with a `NOT_FOUND` error in `errors`, exactly as a nonexistent
organization does. GraphQL is not a second, unscoped path to the same rows.
Nested fields (`facilities`, `emissionsSummary`, `emissionSources`) are
reachable only through that root field, so authorizing the root authorizes
the subtree.

### GET /graphql — the GraphiQL console

`GET /graphql` serves the built-in GraphiQL console as static HTML and is
**deliberately not authenticated**. A browser navigating to a URL cannot
attach an `Authorization` header, so requiring a token to fetch the page
would make the console unreachable — you would need the page in order to
supply the token, and the token in order to load the page.

Nothing is exposed by this. Query execution over GET is disabled
(`allow_queries_via_get=False`), so the GET route can do exactly one thing:
return the console's HTML. A URL carrying a query is refused:

```
GET /graphql?query={__typename}    ->  400  "queries are not allowed when using GET"
```

That holds whether or not a token is supplied, and regardless of the
`Accept` header — GET never reaches a resolver. Every real query is a
`POST`, authenticated exactly as described above.

**Using the console:** open `http://localhost:8000/graphql` (or
`https://localhost:8443/graphql` over TLS), obtain a token from
`POST /api/auth/token`, and paste it into GraphiQL's **Headers** pane:

```json
{ "Authorization": "Bearer <your token>" }
```

Queries then run normally. This console is the intended way to demonstrate
the GraphQL layer; there is deliberately no dedicated frontend screen for
it, since REST is the only write path and the React dashboard already
covers every read the UI needs.

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

## Audit Logs

Every mutating request (`POST`/`PUT`/`PATCH`/`DELETE`) writes one
`audit_logs` row recording who did it, what kind of resource it touched,
which endpoint, and the status code the request ended with. This is done by
a single middleware (`app/middleware/audit.py`), not by per-endpoint calls,
so a newly added write endpoint is audited automatically rather than only
if someone remembers to wire it up.

**What is audited**
- All `POST`/`PUT`/`PATCH`/`DELETE` requests, *except* `POST /auth/register`
  and `POST /auth/token` — logging in is not a data mutation of the kind
  this trail exists to record.
- Failed writes too, with their real status code. A `401`, `404`, or `422`
  is recorded exactly like a `201`; "who tried what and was refused" is the
  half of an audit trail that matters most.

**What is not audited**
- Every `GET` (including `GET /audit-logs` itself), the WebSocket
  endpoints, and GraphQL — which is read-only and has no mutations.

**Field derivation**

| Field | Source |
| --- | --- |
| `user_id` | The authenticated user, taken from the JWT the existing auth dependency already validated. `null` when no user was resolved — e.g. a request rejected with `401`. |
| `action` | `POST` → `CREATE`, `PUT`/`PATCH` → `UPDATE`, `DELETE` → `DELETE`. |
| `resource_type` | Singular snake_case name derived from the path: `/api/organizations` → `organization`, `/api/emission-sources` → `emission_source`, `/api/facilities/1/asset-scan` → `asset_scan`, `/api/reports/generate` → `report` (the trailing verb names the action, not the resource). |
| `resource_id` | The last numeric segment in the path, or `null` if there is none. |
| `endpoint` | The request path, without the query string. |
| `status_code` | The status the response was sent with. |
| `timestamp` | Server time (UTC) at which the row was written. |

**Known limitation — `resource_id` on creates.** It is extracted from the
URL path, so a `POST` to a collection (`POST /organizations`) records
`null`: the new row's id does not exist yet when the request arrives, and
the middleware deliberately does not read response bodies. For a nested
path (`POST /facilities/1/asset-scan`) the recorded id is the parent's — the
`1` — since that is the only id the request itself carries.

**Performance.** The audit write is a background task attached to the
response, so it runs after the response has been sent and adds no latency
to the API call, and it is run in a threadpool so the synchronous database
write never blocks the event loop. A failure to write an audit row is
swallowed and logged; it can never fail the request it was auditing.

### GET /audit-logs
Read back the trail, most recent first. There is no endpoint that creates,
edits, or deletes an audit entry — that is the point of one.

**Scoped to your own actions.** The filter `user_id = <you>` is applied
unconditionally and cannot be overridden: the optional `user_id` query
parameter is ANDed on top, so passing another user's id returns an empty
list rather than their history. `audit_logs` has no `organization_id` — rows
carry a resource type string and an often-null resource id, with no reliable
path back to an organization — so self-scoping is what closes the leak.
While an organization has a single member this is identical in content to
organization-scoping.

One consequence, stated plainly: rows with `user_id: null` — the rejected
unauthenticated attempts the middleware records — are not visible to anyone
through this endpoint.

Query parameters (all optional):

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `resource_type` | string | — | Exact match, e.g. `organization`. |
| `user_id` | int | — | Exact match on the acting user. |
| `limit` | int | `50` | `1`–`200`; outside that range is a `422`. |
| `offset` | int | `0` | Entries to skip, for paging. |

Response `200` — ordered by `timestamp` descending (`id` descending breaks
ties, so paging never skips or repeats an entry):
```json
[
  {
    "id": 202,
    "user_id": 611,
    "action": "CREATE",
    "resource_type": "organization",
    "resource_id": null,
    "endpoint": "/api/organizations",
    "status_code": 201,
    "timestamp": "2026-08-28T07:00:42.125296Z"
  }
]
```
Errors: `401` without a valid bearer token, like every other endpoint;
`422` if `limit`/`offset` are out of range.

---

## Standard Error Shape

All errors follow:
```json
{ "error": { "code": "NOT_FOUND", "message": "Facility 99 does not exist" } }
```
Frontend should branch UI behavior on `error.code`, not on parsing `message` text.

### Why `404` and never `403`

A resource that exists but belongs to another organization returns `404
NOT_FOUND` — byte-for-byte what a resource that never existed returns, same
code and same message wording. There is deliberately no `FORBIDDEN` code.

`403` would confirm that an id is real. With sequential integer ids and open
registration, that turns every endpoint into an enumeration oracle: an
attacker cannot read other tenants' data, but can still map how many
organizations exist, which ids are live, and how fast they are being
created. For a fix whose entire purpose is object-level access control,
leaking the object graph through status codes would undercut it.

The cost is debuggability — "is it missing, or am I not allowed?" is
genuinely harder to answer. That trade is accepted knowingly.

## Status Codes Used
`200` OK · `201` Created · `404` Not Found · `422` Validation Error · `500` Unexpected server error (should be rare — Core Agent should turn known failure cases into 404/422 with a clear `code`, not let them fall through to 500)
