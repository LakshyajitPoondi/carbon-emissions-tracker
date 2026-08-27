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

### POST /reports/generate
Request:
```json
{ "organization_id": 1, "report_period_start": "2026-08-01", "report_period_end": "2026-08-26" }
```
Response `201`:
```json
{
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
```

### GET /reports/{id}
Same shape as above. `404` if not found.

### GET /reports?organization_id={id}
Response `200`: array of report summaries (without the nested `facilities` breakdown — that's only on the detail view).

---

## Standard Error Shape

All errors follow:
```json
{ "error": { "code": "NOT_FOUND", "message": "Facility 99 does not exist" } }
```
Frontend should branch UI behavior on `error.code`, not on parsing `message` text.

## Status Codes Used
`200` OK · `201` Created · `404` Not Found · `422` Validation Error · `500` Unexpected server error (should be rare — Core Agent should turn known failure cases into 404/422 with a clear `code`, not let them fall through to 500)
