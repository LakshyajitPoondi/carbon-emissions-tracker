# Asset Scan — Design Plan

Status: **PROPOSAL — not implemented.** Waiting for review before writing any code.

## Feature recap

User points a webcam at a barcode label on an emission source. The browser
captures a frame and POSTs it to the backend. The backend preprocesses it
(OpenCV), decodes any barcode (pyzbar), runs a pretrained YOLOv8n pass
(ultralytics, CPU-only, no custom training), and returns whatever it found —
including, if the decoded value matches a known emission source, that
source's full record — so the frontend can auto-fill `emission_source_id` on
the consumption-record form.

This plan surfaces **two decisions that need your sign-off before code is
written**, not just the schema question you already flagged. Both are called
out below, then the full point-by-point plan follows.

---

## Decision A — schema change: column, not a mapping table

**Add a nullable `barcode_value` column to `emission_sources`, unique per
facility. Not a separate mapping table.**

Reasoning: a barcode is an alternate lookup key for the *same* entity
(`emission_source`), same cardinality as looking it up by `id` — one source,
one current barcode. A separate `barcode_mappings` table would only be
justified if we needed multiple barcodes per source (e.g. old + reissued
labels) or a reassignment history, and nothing in the brief asks for either.
Adding a table for a case that isn't needed is exactly the kind of premature
abstraction to avoid.

Concretely:
- `emission_sources.barcode_value VARCHAR(255) NULL`
- Unique index on `(facility_id, barcode_value)`. Postgres unique indexes
  treat every `NULL` as distinct from every other `NULL`, so this does **not**
  need a partial `WHERE barcode_value IS NOT NULL` clause — sources without a
  barcode yet simply coexist fine.
- Scoped **per facility**, not globally unique, because nothing guarantees
  barcode values are globally unique across organizations (if a
  vendor-printed barcode type gets reused, or two facilities both invent
  their own simple scheme), and every other lookup in this API is already
  facility-scoped.
- New Alembic migration `0003_add_barcode_value_to_emission_sources.py` —
  additive and nullable, no backfill, safe against the existing data.

**Side effect this creates**: there's currently no way to *set* a barcode on
an emission source after creation (no PATCH/PUT endpoint exists for
`emission_sources` at all). Minimal fix: add `barcode_value` as an optional
field to the existing `POST /emission-sources` request/response. Assigning a
barcode to an *already-created* source is out of scope here (would need a new
PATCH endpoint) — flagging as a known gap, not silently building it.

---

## Decision B — YOLOv8n cannot literally "recognize a barcode," and the plan needs to be honest about what it actually does

This is the one I want you to read carefully before approving.

**The problem**: a pretrained YOLOv8n (COCO weights, no custom training) is
trained on 80 COCO object classes — person, car, bottle, laptop, etc. **There
is no "barcode" class in COCO.** So a stock pretrained YOLOv8n structurally
cannot "localize/verify the barcode region" the way the brief describes,
because it was never trained to recognize what a barcode looks like. This
isn't a tuning problem — it's a *the model has no concept of this object*
problem. The only way to get YOLO to genuinely detect barcodes is to
fine-tune it on a barcode dataset, which directly contradicts "no custom
training needed."

**What actually decodes the barcode, then**: `pyzbar` (a wrapper around the
`zbar` C library) does its own internal scan-and-localize when you hand it a
full frame — it doesn't need an upstream object detector to find the barcode
region first. This is the same approach virtually every "scan a barcode with
your phone" library uses under the hood. So the decode step **works
correctly and fully without YOLO**.

**Proposed honest role for YOLOv8n** (keeps it in the pipeline, doesn't
pretend it does something it can't):
- Run YOLO as a **cheap "is anything even in frame" pre-check / UX gate**,
  not as barcode localization. If YOLO finds zero objects at reasonable
  confidence, that's a strong signal the camera is pointed at a blank
  wall/ceiling/desk — short-circuit immediately with a clear "point the
  camera at the label" message rather than waiting on a decode attempt that
  was never going to succeed.
- `bounding_box` in the response comes from **pyzbar's own decoded symbol
  polygon** (accurate, since it's the thing that actually found the barcode),
  not from YOLO.
- I'm proposing to **drop the numeric "confidence" field from the success
  response** — pyzbar's decode is a deterministic pass/fail, not a
  probabilistic score, so a "confidence" number on a successful decode would
  be fabricated precision. YOLO's own detection confidence only shows up
  (folded into the error `message` string, not a structured field — see
  Decision on error shape below) in the *no-barcode-found* case, as an aid to
  the message ("an object was detected but no readable barcode was found —
  try moving closer or improving lighting" vs. "no object detected at all").

If you want YOLO to genuinely do barcode/label localization as a first-class
signal (not just a presence gate), the only honest path is fine-tuning on a
small barcode dataset — which means dropping "no custom training." I'm not
proposing that; flagging it so you can override this decision if the
presence-gate compromise isn't what you want.

---

## 1. New endpoint(s)

### `POST /facilities/{facility_id}/asset-scan`

Path-scoped by `facility_id` (consistent with the existing
`GET /facilities/{id}/emissions-summary` pattern) rather than passing it in
the body — the barcode lookup is facility-scoped per Decision A.

This is the API's second non-JSON endpoint (after the OAuth2 token endpoint)
— `multipart/form-data` is the correct, standard shape for binary image
upload (base64-in-JSON would inflate payload ~33% and gains nothing here).
`python-multipart` is already a dependency (added for OAuth2 form parsing),
so no new package is needed for this specifically.

**Request** — `multipart/form-data`:
- `image`: file field, JPEG or PNG, captured from the browser's
  `canvas.toBlob()`. Cap at 5MB; anything larger or unreadable as an image →
  `422 VALIDATION_ERROR`.

**Response `200`** — barcode decoded AND matched to a known source:
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
`bounding_box` is pixel coordinates in the submitted image, from pyzbar's
decoded symbol polygon. No `confidence` field (see Decision B).

**Errors** (both `422`, both real/expected cases per your point 3 & 4, not
edge cases — see next two sections): `NO_BARCODE_DETECTED`,
`BARCODE_NOT_MATCHED`. Also standard `404` if `facility_id` doesn't exist,
`422 VALIDATION_ERROR` if the upload is missing/unreadable/oversized — same
pattern as every other endpoint.

### Modification to `POST /emission-sources` (existing endpoint)

Add optional `barcode_value` to the request and response — this is a change
to an *existing* contracted shape, not just a new addition, so it formally
needs the Contract Change Protocol (see below), not just a new section.

---

## 2. Schema change

Covered in Decision A above: nullable `barcode_value` on `emission_sources`,
unique per `(facility_id, barcode_value)`, new migration
`0003_add_barcode_value_to_emission_sources.py`.

---

## 3. Barcode decodes, but matches no emission_source

Real, expected case (e.g. a label was printed but the source was never
registered, or registered in a different facility). Following the existing
`NO_MATCHING_FACTOR` precedent (a similarly-shaped "valid input, no matching
resource" case, modeled as `422` not `404`, since nothing about the request
itself was invalid):

```json
{ "error": { "code": "BARCODE_NOT_MATCHED", "message": "Barcode 'ENSRC-00042' does not match any emission source in facility 1" } }
```
The decoded value is folded into the message text (the standard error shape
is strictly `{code, message}` — no extra fields — so this keeps to the
existing convention rather than inventing a per-endpoint deviation).

## 4. YOLO/OpenCV finds no decodable barcode at all

Also real and expected (camera pointed at nothing, bad lighting, blurry
frame). Distinct code from case 3, since here we never got a decoded value:

```json
{ "error": { "code": "NO_BARCODE_DETECTED", "message": "No readable barcode found in frame" } }
```
Per Decision B, if YOLO's presence-gate did find *some* object but pyzbar
still couldn't decode a barcode from it, the message differs slightly
("An object was detected but no readable barcode was found — try moving
closer or improving lighting") to give the user actionable feedback, but the
`code` stays `NO_BARCODE_DETECTED` in both sub-cases — the frontend doesn't
need to branch on that distinction, only the message text differs.

---

## 5. Where this fits in docs/api-contract.md

New `## Asset Scan` section, placed directly after `## Emission Sources`
(it's conceptually an extension of that resource). Also requires editing the
existing `## Emission Sources` section's request/response examples to add
`barcode_value`. Per `agents/core.md`'s API Contract Responsibilities, this
combination (new section + modifying an existing contracted shape) goes
through the Contract Change Protocol:

```
CONTRACT CHANGE REQUEST
Current contract: POST /emission-sources request/response has no barcode_value field; no Asset Scan section exists.
Proposed contract: Add optional barcode_value to POST /emission-sources request+response.
  Add new "## Asset Scan" section: POST /facilities/{facility_id}/asset-scan (multipart image upload),
  200 with decoded_value/bounding_box/emission_source, 422 NO_BARCODE_DETECTED, 422 BARCODE_NOT_MATCHED.
Reason: Asset Scan feature (barcode + OpenCV + YOLOv8n merged requirement)
Frontend impact: EmissionSourceCreateRequest/Response types gain an optional field;
  new webcam-capture UI needed on the Consumption/Setup flow (not designed in this plan — backend-scoped only)
Breaking change: NO (barcode_value is optional/nullable everywhere)
```

---

## 6. New Python packages & Docker friction

| Package | Purpose | Friction to flag now |
|---|---|---|
| `opencv-python-headless` (not plain `opencv-python`) | Frame preprocessing | Use the **headless** build specifically — plain `opencv-python` pulls in GTK/Qt GUI bindings that are dead weight in a server container and are a common source of build failures on slim Debian images. Even headless builds commonly need `libglib2.0-0` present via apt; confirm at build time whether `libgl1` is also still needed (version-dependent). |
| `pyzbar` | Barcode decoding | This is a thin Python wrapper — **it does not bundle the native `zbar` library on Linux** (unlike its Windows wheel, which does). Without `apt-get install -y libzbar0` in the Dockerfile, `import pyzbar.pyzbar` raises `ImportError: Unable to find zbar shared library`. This is the single most likely install failure — flagging explicitly so it doesn't cost a debugging session. |
| `ultralytics` | YOLOv8n inference | Pulls in `torch` (PyTorch) as a transitive dependency. **Plain `pip install torch` on Linux resolves a CUDA-enabled wheel by default** (multiple GB), which is pure waste on a CPU-only machine and will make the Docker build slow and the image huge. Must explicitly install the CPU-only build first via `pip install torch --index-url https://download.pytorch.org/whl/cpu`, *then* install `ultralytics` so it finds torch already satisfied. |

Net effect: expect the backend image to grow by roughly 1–1.5GB even with the
CPU-only torch wheel, and the build to take noticeably longer. That's an
expected tradeoff of this feature, not a bug — flagging so it's not a
surprise.

Dockerfile apt-get line needs to become:
```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev libzbar0 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*
```
(`curl` added for the model-weight download in point 8 below.)

---

## 7. Model loading strategy — load once at startup, not per-request

Use FastAPI's `lifespan` context manager (the current, non-deprecated
pattern — not `@app.on_event("startup")`) to load the model exactly once
into `app.state`:

```python
from contextlib import asynccontextmanager
from ultralytics import YOLO

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.yolo_model = YOLO("/app/models/yolov8n.pt")
    yield

app = FastAPI(lifespan=lifespan, ...)
```

The asset-scan router accesses it via a small dependency
(`def get_yolo_model(request: Request): return request.app.state.yolo_model`)
— never `YOLO(...)` re-instantiated inside the route handler, which would
reload weights from disk on every single scan (slow, and defeats the entire
point of loading at startup).

Note: with `--reload` (used in the dev Dockerfile CMD), the lifespan re-runs
on every code-change reload, adding a ~1-2s model-load delay after each hot
reload during development. That's acceptable dev-time overhead, not a
demo-time concern — the actual demo run wouldn't be sitting mid-edit when
someone scans.

---

## 8. Baking YOLOv8n weights into the Docker image

Dockerfile addition (after the pip install layer, before `COPY . .`, so
source-only changes don't invalidate this layer's cache):

```dockerfile
RUN mkdir -p /app/models \
    && curl -L -o /app/models/yolov8n.pt \
       https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt
```

Explicit `curl` against a pinned release URL, not
`python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"` — pinning an
exact URL is deterministic and reviewable, rather than depending on
`ultralytics`'s internal download-resolution logic and whatever release tag
that library version defaults to. The exact tag (`v8.3.0` above is a
placeholder) needs confirming against whatever `ultralytics` version ends up
pinned in `requirements.txt` at implementation time.

**A real gotcha this creates, given the current `docker-compose.yml`**:
`backend` bind-mounts the entire host directory over the container —
`volumes: - ./backend:/app`. That mount **shadows anything baked into the
image at `/app/*`** that doesn't also exist on the host side, because the
bind mount wins at runtime. So baking the weights into the image alone is
**not sufficient** for local dev with the current compose setup — the file
would exist in the image layer but disappear at container start once the
host directory mounts over `/app`.

Two ways to resolve this, need your call:
- **(a)** Also keep a copy at `backend/models/yolov8n.pt` on the host,
  gitignored (weights are ~6MB, small enough to not worry about repo bloat
  either way, but I'd default to gitignored + a one-time local fetch step
  documented in the README, matching how `postgres_data/` is already
  gitignored). The Dockerfile's bake step remains the source of truth for a
  fresh clone / CI / any non-bind-mounted deployment; the host copy is purely
  so local dev (which always uses the bind mount) sees the same file.
- **(b)** Narrow the compose bind mount (e.g. mount `./backend/app:/app/app`
  and `./backend/tests:/app/tests` individually instead of the whole
  `./backend:/app`) so `/app/models` from the image layer is never shadowed.

I'd default to **(a)** — it's a one-line addition (a documented fetch
command) versus restructuring a mount that every other file in this project
currently depends on working the way it does. Flagging both so you can pick.

---

## Frontend implication (not designed here — out of scope for this plan)

The frontend will need a webcam-capture UI (`getUserMedia` + a canvas frame
grab + `FormData` upload) on the Consumption flow, feeding
`emission_source_id` once a scan resolves. Not designing that here since this
plan is scoped to the backend per `agents/core.md` — flagging so it isn't
forgotten, and so the Contract Change Protocol above gives the Frontend Agent
enough to plan against once this is approved.

---

## Open questions needing your explicit decision

1. **Decision B** — approve the "YOLO as presence-gate, pyzbar does the real
   decode/localize" compromise? Or do you want true ML-based barcode
   localization badly enough to reconsider "no custom training"?
2. **Point 8's bind-mount gotcha** — option (a) (host-side gitignored copy,
   my default) or (b) (narrow the compose mount)?
3. Endpoint path — `POST /facilities/{facility_id}/asset-scan` (my
   recommendation, matches the existing `emissions-summary` pattern) or do
   you want it elsewhere (e.g. flat `POST /asset-scan` with `facility_id` in
   the body, matching the feature's name more literally)?
4. Confirm dropping the `confidence` field from the success response
   (Decision B) is acceptable, versus wanting *some* number there even if
   it's not truly a decode-confidence score.

Waiting for your review before writing any code.
