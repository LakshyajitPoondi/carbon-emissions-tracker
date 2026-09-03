# claude_context.md — Carbon Emissions Tracking Platform: agent/session context

> **Meta-rule, read first:** This file is the persistent memory for whoever
> (human or LLM/agent) works on this project next. It is NOT a one-time
> snapshot. Every session that does real work on this repo — implements a
> task, changes a decision, discovers a gap, fixes a bug — MUST update this
> file before finishing, in the same terse, structured, fact-dense style
> used below. Append new history entries to "Work completed" in
> chronological order; do not delete old entries, only mark them superseded
> if something changes. Do not write prose paragraphs of narrative — write
> the way this file is written: short bullets, concrete facts, file paths,
> exact values. A future agent should be able to read this file alone and
> know what exists, why, what's still missing, and what rules to follow,
> without re-deriving any of it from scratch. Keep it in English.

## What this project is

College project: a Carbon Emissions Tracking Platform. Organizations track
facilities, which track emission sources (categorized ENERGY / FUEL /
RESOURCE), which log consumption records; the backend converts consumption
into kg CO2e using cited emission factors. Presentation layer maps the
three categories onto real GHG Protocol scopes (see "Scope 1/2/3
relabeling" below) — this project consistently treats carbon-accounting
correctness and citation as a real constraint, not just UI copy.

## Tech stack

- Backend: FastAPI + SQLAlchemy + Alembic + PostgreSQL. Python 3.12.
- Read-only GraphQL layer alongside REST: strawberry-graphql. REST is the
  source of truth for all writes; there is no GraphQL Mutation type.
- Async work (report generation): Celery + Redis.
- Live updates: native WebSockets (not socket.io).
- Frontend: React + TypeScript + Vite, react-router-dom. No UI component
  library, no icon library — inline SVG icons, hand-rolled CSS with custom
  properties (`frontend/src/index.css`).
- Auth: JWT (register/login).
- Deployment: Railway (backend, celery-worker, Postgres, Redis as separate
  services) + Vercel (frontend). Local dev via `docker-compose.yml`.
- Repo layout: `backend/`, `frontend/`, `Docs/` (capitalized — verify on
  disk before assuming `docs/`), `Agents/` (agent-facing convention docs:
  `Agents/core.md`, `Agents/frontend.md` — read these too, they may be more
  current than this section), `k8s/` (a parallel local-Kubernetes deploy
  target, not the real Railway/Vercel path).

## Domain model

`organizations -> facilities -> emission_sources -> consumption_records`.
`emission_sources.source_type` enum: `ENERGY | FUEL | RESOURCE`.
`emission_factors` is seeded reference data (factor value + unit + region +
validity window + `source_reference` citation) used to convert a
consumption amount to kg CO2e. Seeded factors are real and cited:
- ENERGY: CEA India grid emission factor (kg CO2e/kWh), CEA CO2 Baseline
  Database, Version 19.
- FUEL: IPCC 2006 Guidelines, diesel oil default factor (kg CO2e/litre).
- RESOURCE: GHG Protocol Scope 3 Purchased Goods, Portland cement, India
  average (kg CO2e/kg).

`emission_sources.barcode_value` (nullable) — added early, unused by the
frontend until the Product Library task exposed it via a new PATCH
endpoint (see history).

`organization_members` (user_id, organization_id, role) is the entire
authorization backbone — see "Authorization model" below.

`Product` (added by Product Library task) — organization-scoped, manually
entered catalog: name, nullable-but-unique-per-org barcode, composition
(free text), emissions_value/unit/description + source_reference. Reference-only
by default. Since item 19, OWNER/ADMIN may explicitly set `consumption_unit`
and `consumption_source_type` to enable Product consumption using its own
declared per-unit kg CO2e value (not the seeded emission-source factors).

`Product.barcode_image` (added by item 15) stores the generated PNG bytes.
Omitting/blanking `barcode` on create allocates an organization-local GS1
restricted-circulation EAN-13 (`20...`) and persists its PNG. Valid supplied
EAN-13 values also get a PNG; arbitrary legacy barcode strings remain
accepted but have no image. `GET /api/products/{id}/barcode-image` is the
read-only, VIEW-gated image surface.

## Authorization model (RBAC)

Central matrix in `backend/app/authorization.py`. Three roles:
`OWNER`, `ADMIN`, `EMPLOYEE` (DB CHECK constraint on
`organization_members.role`). Three action tiers via `OrganizationAction`
enum: `VIEW`, `ENTRY`, `WRITE`.
- `VIEW` and `ENTRY`: all three roles.
- `WRITE`: `OWNER` + `ADMIN` only. `ADMIN` is fully equivalent to `OWNER`
  everywhere except it cannot be the one demoted/removed if doing so would
  leave zero OWNERs (see membership management below).
- `EMPLOYEE` can view everything and create consumption records (ENTRY),
  but cannot create/edit/delete facilities, emission sources, products,
  reports, or manage membership.
- Default for any call site that doesn't explicitly classify its action:
  `WRITE` (fail-closed — a future endpoint that forgets to classify itself
  never accidentally grants EMPLOYEE access).
- Enforced consistently across every REST router, the GraphQL resolver, and
  the WebSocket handler — not just REST.
- Every denial (missing resource, not-your-org, or role-denied) returns the
  *same* masked `404 NOT_FOUND` — see "404-masking" below. Role denial is
  deliberately made indistinguishable from "doesn't exist."
- `GET /organizations` / `POST /organizations` / `GET /organizations/{id}`
  responses include the caller's `role` for that org (contract change,
  approved and merged — see Docs/api-contract.md).

**Former gap, now closed:** as of RBAC's initial merge, there was no way to
actually add a second member to an org or grant ADMIN/EMPLOYEE —
`POST /organizations` was the only path that ever created a membership row,
and it always grants OWNER. The "Membership management" work (item 13
below) closed this — join codes, join requests, approval/rejection, member
listing, role changes, and removal are all implemented and merged.

## 404-masking convention (established early, load-bearing everywhere)

`backend/app/authorization.py`'s module docstring is the canonical
explanation. Every access denial — resource doesn't exist, belongs to
another organization, or the caller's role doesn't permit the action —
returns the identical `404 NOT_FOUND` shape. This is deliberate: with
sequential integer IDs and open registration, a `403` would confirm which
IDs exist and let anyone map the object graph. New endpoints must follow
this; do not introduce `403` for role denials.

## Standard error contract

`{"error": {"code": "SOME_CODE", "message": "human text"}}` — see
`backend/app/schemas/error.py`. Business-rule errors use `422` with a
specific `SCREAMING_SNAKE_CASE` code (examples already in use:
`BARCODE_ALREADY_ASSIGNED`, `BARCODE_NOT_MATCHED`,
`NO_BARCODE_DETECTED`, `JOIN_REQUEST_ALREADY_PENDING`,
`ALREADY_ORGANIZATION_MEMBER`, `JOIN_REQUEST_ALREADY_DECIDED`,
`LAST_OWNER_REQUIRED`). Access/existence errors always use the masked
`404 NOT_FOUND` from the section above, never a bespoke code.

## API contract governance

`Docs/api-contract.md` (verify exact casing on disk) is the frozen,
authoritative REST/GraphQL contract. **Any change to request/response
shape or a new endpoint requires: propose the exact change in writing ->
get explicit human approval -> only then implement.** This has been
followed successfully for every schema/endpoint change so far (RBAC's new
`role` field, Product Library's whole CRUD surface, the emission-source
PATCH endpoint, and the in-progress membership-management endpoints all
went through this gate). Do not skip it, even for something that feels
additive/non-breaking.

## Git / workflow rules (strict, established from the start)

- **All git state-changing operations — branch, add, commit, push, merge —
  are human-run only.** An agent (or Claude) may run `git status`,
  `git diff`, `git log`, `git show`, `git cat-file`, `git rev-list`,
  `git merge-base` to orient itself, but never mutate repo state.
- Convention (not always followed lately, see note): each real code task
  gets its own short-lived branch off current `main`, named
  `agent/<area>/<task>` (e.g. `agent/core/rbac`, `agent/frontend/graphql-
  dashboard`). **Actual practice as of this handoff has drifted**: the
  human chose to keep building later tasks (Product Library, Theme
  Overhaul, Membership Management) directly on top of the `agent/core/rbac`
  branch rather than cutting fresh branches each time, once that branch was
  already merged to `main`. Functionally harmless (branch was identical to
  `main` at the time), but branch names no longer describe their contents.
  Don't assume a branch name tells you what's on it — check
  `git log <branch> --oneline` and `git merge-base <branch> main`.
- Commit message style: short, plain, imperative title, no conventional-
  commit prefix (`feat:`, etc. — one agent suggested a `feat(frontend):`
  prefix and it was explicitly normalized away to match existing style).
  Examples already in history: `Role Based Access Control`,
  `Add organization-scoped Product Library (barcode, composition,
  emissions) and emission-source barcode editing`, `UI Theme Overhaul`,
  `GHG Protocol Scope 1,2,3`.
- **Known repo hygiene issue, ignore it:** nearly every tracked file shows
  as "modified" under `git status`/`git diff` due to pre-existing CRLF/LF
  line-ending churn (whole-file 1:1 line insert/delete, zero real content
  change — confirmed via `git diff --ignore-space-at-eol` showing empty
  diffs on affected files). This is old and unrelated to any task. Don't
  try to fix it as a side quest; use `--ignore-space-at-eol` to see real
  diffs through the noise.
- **Local git tooling gotcha:** `git status` and `git fetch` can leave a
  stale, empty `.git/index.lock` (and `.git/objects/maintenance.lock`) if
  interrupted, which then makes the user's own terminal report "another
  program is using git." If this happens: confirm the lock file is 0 bytes
  and stale, then delete it (may need the human to delete it directly if
  the agent's shell lacks delete permission on that folder). Prefer
  index-non-touching commands (`log`, `show`, `cat-file`, `rev-list`,
  `diff <ref>..<ref> -- <path>`) over `status`/`fetch` when a human might
  have a terminal open concurrently.
- Trust but verify: when a human relays an agent's "task complete" report,
  independently check the actual repo/code before treating it as done —
  this has been done for every merged task and caught zero real problems,
  but is worth continuing (branch names, migration chains, dependency
  diffs, and role-gating logic have all been spot-checked this way).

## Deployment specifics (Railway + Vercel) — things that have actually bitten this project

- Railway's backend "Custom Start Command" chains
  `alembic upgrade head && python -m app.seed && uvicorn ...` — migrations
  and seeding run on **every** deploy, not just the first.
- `app/seed.py` is idempotent: always seeds/skips reference
  `emission_factors`; optionally seeds a dedicated public demo only when
  `SEED_DEMO_ACCOUNTS=true`. Demo seeding is off by default, scoped to
  `Demo Organization`, and never overwrites existing rows. Railway runs
  the seed on every backend deploy, so this variable is the production
  opt-in switch. Setting it false after a prior true deploy stops seed
  work but does not delete/revoke already-created demo accounts.
- **Railway does not read `docker-compose.yml`.** The Celery worker's start
  command must be set manually in the Railway dashboard (Settings ->
  Deploy -> Start Command) for the `celery-worker` service:
  `celery -A app.celery_app worker --loglevel=info --concurrency=2
  --max-tasks-per-child=100 --without-gossip --without-mingle
  --without-heartbeat`. `--concurrency=2` is not optional — Celery's
  prefork pool defaults concurrency to the *host's visible CPU count*, not
  the plan's actual share, which alone caused ~704.6MB usage (measured)
  against Railway's 500MB limit and a guaranteed OOM crash; `concurrency=2`
  measured at ~142.8MB. This was root-caused properly: an earlier
  hypothesis blamed PyTorch/ML imports leaking into the worker process —
  that was investigated and **refuted** (the worker's import graph
  contains no torch/cv2/ultralytics; `backend/tests/test_celery_imports.py`
  is a regression guard that fails if a future import reintroduces it).
  The concurrency/memory issue was the real and *only* cause.
- The FastAPI backend process itself legitimately loads PyTorch + YOLOv8n
  at startup (for the Asset Scan endpoint): ~340.7MB at rest, ~462-474MB
  after inference. If the backend service is on the same 500MB tier as the
  worker, that's thin headroom — worth checking the actual tier before
  raising traffic, not assumed safe.
- `CORS_ALLOWED_ORIGINS` is a Railway **dashboard environment variable**
  for the backend service — NOT read from the repo's `.env` (which only
  holds `http://localhost:5173` for local dev). It must contain the exact
  current frontend origin(s), comma-separated, and the backend service
  must be redeployed after changing it. Common failure mode already seen
  once: a CORS error on the login/`/token` call after a Vercel deployment
  change — turned out to be the human testing against the wrong URL (a
  preview URL, not production), not an actual misconfiguration, but this
  failure mode is real and worth checking first: (1) exact frontend origin
  in the address bar vs (2) Railway's `CORS_ALLOWED_ORIGINS` vs (3)
  Vercel's `VITE_API_BASE_URL`/`VITE_USE_MOCK_API`.
- Frontend env vars (`VITE_USE_MOCK_API`, `VITE_API_BASE_URL`, and the
  opt-in `VITE_ENABLE_DEMO_ACCESS`) must be set
  in **Vercel's** project settings for production. Contrary to an older
  assumption, `frontend/.env.local` is currently tracked by this repo
  (`.gitignore` ignores only the exact root `.env` name); do not rely on
  that file for choosing Vercel Production vs Preview values — use the
  dashboard's environment-scoped variables and rebuild.
- Verified (as of RBAC + Product Library + Theme Overhaul merge): none of
  that work added a new npm or pip dependency, nor a new required env var.
  Alembic migration chain is strictly linear
  (`0001 -> 0002 -> ... -> 0008_add_products ->
  0009_membership_lifecycle -> 0010_product_barcode_images`, each
  `down_revision` checked). Merge order matters when multiple feature
  branches touch migrations — always confirm the chain stays linear
  (no forked heads) before/after merging.
- Vercel (frontend) typically finishes deploying faster than Railway
  (backend rebuilds a heavier image, torch/opencv included) — a 404 or
  missing-route error right after a push is often just deploy lag on the
  backend side, not a real bug. Check the Railway dashboard's deploy status
  before assuming code is broken. (One real instance of this: Products page
  404'd right after merge, and the error was `UNKNOWN_ERROR`/generic —
  which is itself a tell, since this app's *real* 404s always carry the
  `{"error":{"code":"NOT_FOUND",...}}` shape; a plain-shaped 404 usually
  means the request hit a backend that doesn't have the route yet.)

## Testing methodology

- Backend: `pytest tests/ -v` — full suite run before/after every task.
  New tasks add targeted regression tests
  (`test_celery_imports.py`, `test_roles.py`, etc.). ~229 passing as of the
  Product Library merge; 242 passing after the sign-in/demo-seed work;
  249 passing after item 15.
- Frontend: `npx tsc -b --noEmit` (must be `-b`, not a bare `--noEmit` —
  `frontend/tsconfig.json` is a solution-style config with `"files": []`
  referencing `tsconfig.app.json`/`tsconfig.node.json`, so a bare
  `--noEmit` silently checks nothing and exits 0 regardless of real type
  errors — verified with a deliberate type error). `npm run build`.
  `npm run lint` (oxlint).
- `git diff --check` for line-ending sanity (expect only the known CRLF
  notices, nothing else).
- CI: `.github/workflows/ci.yml` runs backend pytest (against real
  Postgres/Redis service containers) + frontend typecheck/build, on every
  push and PR, all branches, no path filters.
- Manual verification is always required in addition to automated tests:
  real (non-mock, `VITE_USE_MOCK_API=false`) UI walkthroughs of the actual
  feature, cross-checking GraphQL numbers against REST/DB values, testing
  the actual role-denial paths (not just the happy path), testing declared
  edge cases live rather than assuming they're covered.
- This project has a consistent norm of **not rounding "should work" up to
  "verified"** — every task summary is expected to state plainly what was
  actually confirmed vs. what couldn't be tested (e.g. missing non-zero
  test data, a browser permission block preventing a cleanup step) rather
  than claiming full verification anyway.

## How work actually gets done here (the process, not just the code)

Real implementation happens through a **local coding agent working
directly against the repo** on the human's machine
(`C:\Users\<user>\Carbon Footprint College Project`), not by an assistant
editing the repo wholesale in one shot. The pattern that has worked well
and should continue:

1. Write a **self-contained prompt file** for the agent: full project
   context (agents start with no memory of prior sessions), the task
   broken into numbered steps, explicit **non-goals**, constraints
   (frontend-only/backend-only, branch policy, don't touch
   `Docs/api-contract.md` without approval, don't commit/push), a
   verification checklist, and the exact deliverable/summary format
   expected back.
2. If the task will touch the API contract or any access-control surface,
   the prompt explicitly requires the agent to **stop and propose the
   change in writing before implementing** — this "propose, then approve,
   then implement" loop has been used repeatedly and caught real design
   questions before code was written (join-code format, error codes, last-
   owner safeguard, etc.).
3. The agent reports back with a structured summary: what changed, why,
   the exact contract/decisions made, and verification results.
4. Before treating the report as ground truth, independently spot-check
   the actual repo (read the real files, check migration chains, diff
   against the base branch for new dependencies) — don't just trust the
   prose summary.
5. The human performs all git mutations (branch/commit/push) themselves;
   agents and assistants only ever read git state.

## Work completed (chronological)

1. **Base app**: JWT auth; organizations/facilities/emission_sources/
   consumption_records CRUD; `emission_factors` seeded with real cited
   values (see Domain model above).
2. **Object-level authorization (BOLA) fix**: `organization_members` table
   introduced; established the 404-masking convention (see above) as the
   permanent access-denial contract.
3. **Read-only GraphQL layer**: `organization(id)` query with nested
   `facilities`/`emissionsSummary`, resolved via DataLoaders (no N+1).
   JWT-protected on `POST`; `GET` (GraphiQL console) left unauthenticated
   deliberately so the console works, with the real query auth enforced at
   `POST`.
4. **WebSocket live updates** for facility/organization emissions.
5. **Celery + Redis async report generation**, then an OOM crash and its
   fix — see "Deployment specifics" above for the full root-cause story
   (concurrency, not ML imports). Regression guard:
   `backend/tests/test_celery_imports.py`.
6. **Kubernetes manifests** (`k8s/`) — a parallel local-cluster deploy
   target; not the real production path (that's Railway + Vercel).
7. **Asset Scan feature**: webcam frame -> `pyzbar` barcode decode ->
   optional YOLOv8n presence-gate -> match against
   `emission_sources.barcode_value` within a facility. Fully read-only, no
   DB writes (verified by code read — no `db.add`/`db.commit` anywhere in
   that path). Also ZPL label generation (`backend/app/services/
   labels.py`). Endpoint: `POST /facilities/{id}/asset-scan`.
8. **GraphQL-powered Organization Overview page** (`/overview`): single
   GraphQL query, per-facility category breakdown + org-wide total,
   plain `fetch` (no Apollo/urql — deliberately kept dependency-free).
9. **Scope 1/2/3 relabeling** (frontend presentation only, no data/contract
   change): `FUEL -> Scope 1 (Stationary Combustion)`,
   `ENERGY -> Scope 2 (Purchased Energy)`,
   `RESOURCE -> Scope 3 (Purchased Goods)`. All three existing categories
   turned out to map onto real GHG Protocol scopes (RESOURCE/cement is
   genuinely Scope 3 Purchased Goods per its own seeded citation) — no
   "non-GHG" bucket was needed, which was the original (incorrect)
   assumption going in. Central mapping:
   `frontend/src/utils/sourceTypePresentation.ts`
   (`SOURCE_TYPE_PRESENTATION`, `GHG_SCOPE_SOURCE_TYPES`,
   `GHG_SCOPE_TOTAL_CAPTION`) — every page (Dashboard, Overview, Reports,
   Setup) reads from this one place; do not duplicate label strings
   per-component.
10. **RBAC** (`OWNER`/`ADMIN`/`EMPLOYEE`) — see "Authorization model"
    above for the full design. Migration `0007_expand_organization_roles`.
    Merged to `main`.
11. **Product Library** — see "Domain model" above.
    Migration `0008_add_products`. New endpoints:
    `POST/GET/PATCH/DELETE /api/products`,
    `PATCH /api/emission-sources/{id}` (new — didn't exist before; needed
    to expose the long-unused `barcode_value` field in the Setup form).
    Frontend: new `/products` page. Merged to `main`.
12. **UI Theme Overhaul** (frontend-only, purely structural/visual):
    replaced the old top-only `NavBar.tsx` with
    `frontend/src/components/AppShell.tsx` — left sidebar (grouped nav:
    Workspace/Tracking/Insights/Account), inline SVG icons (no icon
    library), mobile drawer below 780px, fixed top bar, edge-to-edge
    content layout, purple/dark accent theme
    (`--color-primary: #7c3aed`, sidebar `#191326`, full token list in
    `frontend/src/index.css`). All existing pages, functionality, and
    role-gating (`SetupPage.tsx`/`ReportsPage.tsx`'s EMPLOYEE-hiding logic)
    preserved untouched. No new dependencies. A visual reference app was
    used for *layout structure and color direction only* — its
    domain-specific content (map, alert cards, demo banner, its own nav
    labels) was explicitly excluded. Merged to `main`.
    **Palette superseded by item 15; AppShell/layout remains current.**
13. **Membership management — DONE, implemented and merged.** Fixes the
    RBAC gap from item 10 (there was no way to add a second member to an
    org or grant ADMIN/EMPLOYEE). Design as approved:
    - Real signup flow: after account creation, choose "create an
      organization" (existing, unchanged) or "join an organization" (via
      join code).
    - Join codes: format `ORG-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX`, 120 bits of
      randomness, unambiguous uppercase alphabet, case-insensitive/trimmed
      input, generated at org creation (existing orgs backfilled via
      migration), unique DB constraint, stored as opaque plaintext (not
      hashed — justified because it must be redisplayed to OWNER/ADMIN
      indefinitely on the Members page), visible only to OWNER/ADMIN,
      regeneration invalidates the old code but not already-pending
      requests (linked by org FK, not code value), never included in
      ordinary organization responses/listings, unknown/malformed codes
      return the identical masked 404.
    - New endpoints (all approved and implemented):
      `GET/POST .../join-code(/regenerate)` (WRITE),
      `POST /join-requests` (authenticated, body `{"join_code": "..."}`),
      `GET /join-requests/me` (self-scoped — lets a user see their own
      pending state after reload),
      `GET .../join-requests` (WRITE, list pending for an org),
      `POST .../join-requests/{id}/approve` (WRITE, body `{"role": "..."}`,
      atomic — creates membership + marks approved in one transaction with
      concurrency protection),
      `POST .../join-requests/{id}/reject` (WRITE),
      `GET .../members` (VIEW — visible to EMPLOYEE too),
      `PATCH .../members/{user_id}` (WRITE, change role),
      `DELETE .../members/{user_id}` (WRITE, 204).
    - New error codes: `JOIN_REQUEST_ALREADY_PENDING`,
      `ALREADY_ORGANIZATION_MEMBER`, `JOIN_REQUEST_ALREADY_DECIDED`,
      `LAST_OWNER_REQUIRED` (all 422); everything else falls back to the
      standard masked 404.
    - Policy: OWNER and ADMIN can both manage any member, including
      themselves or another admin. Self-removal/self-demotion allowed as
      long as another OWNER remains. Promotion to OWNER via approve/PATCH
      is allowed (consistent with ADMIN already being fully OWNER-
      equivalent elsewhere). The **only** blocked operation is one that
      would leave an organization with zero OWNERs
      (`LAST_OWNER_REQUIRED`). EMPLOYEE can view the member list but not
      the join code, pending requests, or any mutation. No changes to the
      RBAC matrix itself — this reuses `VIEW`/`ENTRY`/`WRITE` as-is.
    - One pending request per (user, org) enforced via a partial unique
      DB index, not just application logic.
    - Frontend: replace the old "Load existing by ID" first-run option
      with "Join an organization"; a new `/members` page (member list +
      role-appropriate management controls, join code display for
      OWNER/ADMIN, pending-request approve/reject); `GET /join-requests/me`
      used so a pending request persists visibly across reloads.
    - Implemented directly on the `agent/core/rbac` branch (the human
      explicitly chose not to cut a fresh `agent/core/membership-
      management` branch, since `agent/core/rbac` was already identical to
      `main` at the time). Branch name does not match its contents — check
      `git log` before assuming what's on a branch by its name.
    - Key files: migration
      `backend/alembic/versions/0009_add_membership_lifecycle.py`;
      `backend/app/routers/memberships.py`;
      `backend/app/models/organization_join_request.py`;
      `backend/app/schemas/membership.py`;
      `backend/app/tests/test_memberships.py` (10 focused tests, all
      passing; 239 passing in the full backend suite after this merge);
      frontend: `frontend/src/pages/SetupPage.tsx` (create-or-join
      first-run flow — registration now always lands on Setup so a new
      user immediately sees the choice, a routing edge case found and
      fixed during browser verification),
      `frontend/src/pages/MembersPage.tsx` (new, role-aware member
      management UI), `frontend/src/types/membership.ts`.
    - Verified end-to-end with a real two-account walkthrough: join
      request persisted as pending, approval granted EMPLOYEE, a
      subsequent promotion granted ADMIN capabilities, removal produced
      the expected masked 404 for the removed user. Migration verified
      both against an existing database and by replaying the entire
      migration history against a fresh blank database.
    - Noted in passing (not touched, not this task's concern): `alembic
      check` flags a pre-existing, unrelated drift between the `users`
      model and its migration around the `email` column — predates this
      task, detected no drift *from* the new membership schema, left as-is.
    - Cleanup note: the temporary blank verification DB and its test
      membership were removed after verification, but a disposable
      verification organization/accounts created during the real
      two-account walkthrough were intentionally left in the local dev
      database (harmless test data, not production).
14. **Sign-in redesign + opt-in demo environment** (implemented on
    `agent/core/refinements`; no contract/schema change):
    - Public auth routes render a centered sign-in card (original purple
      palette superseded by item 15's pastel-green theme) and
      never mount the AppShell sidebar. Authenticated shell/nav is
      unchanged. Demo Access buttons fill credentials only; they do not
      submit automatically.
    - Frontend demo panel is gated by `VITE_ENABLE_DEMO_ACCESS=true`;
      backend seed is independently gated by
      `SEED_DEMO_ACCOUNTS=true`. Both default false.
    - Public demo credentials: `admin-demo@gmail.com` (OWNER) and
      `employee-demo@gmail.com` (EMPLOYEE), both password
      `DemoPass123!`.
    - Demo fixture: 7 memberships (1 OWNER / 2 ADMIN / 4 EMPLOYEE), 3
      facilities, 8 sources covering ENERGY/FUEL/RESOURCE, 24 August 2026
      consumption records + calculations, 5 Products, and 1 FINAL report.
      Five stable internal-use EAN-13 PNGs live under
      `backend/demo_assets/barcodes/`; generator is dependency-free.
    - Product barcode field is `products.barcode` (the task prompt called
      it `barcode_value`). Asset Scan currently resolves only
      `emission_sources.barcode_value`, so the Product PNGs decode as
      EAN-13 but do not resolve in the app's Asset Scan endpoint. No silent
      API-contract expansion was made; product scanning needs a separate
      proposal/approval.
    - Audit-log audit found a partial end-to-end feature: migration/model,
      request middleware, REST endpoint, contract, and backend tests exist;
      no frontend API method/page/nav exists.
    - Local seed counts before -> after (unchanged on second run): orgs
      `0 -> 1`, memberships `0 -> 7`, facilities `0 -> 3`, sources
      `0 -> 8`, records `0 -> 24`, calculations `0 -> 24`, products
      `0 -> 5`, reports `0 -> 1`. Real non-mock Owner and Employee login
      walkthroughs passed; Dashboard/Overview/Reports/Products/Members
      showed seeded data. Full backend suite: 239 before, 242 after.
      Frontend typecheck/build/lint passed (lint has existing warnings).
    - Last-used-organization auto-selection remains proposal-only. No
      user column, migration, login response change, or endpoint was added.
15. **Product barcode generation + dual Asset Scan + green theme**
    (implemented on `agent/core/refinements`; approved contract update):
    - Product create with omitted/blank barcode now allocates a unique
      per-organization restricted-circulation EAN-13 and stores a generated
      PNG in `products.barcode_image`; migration
      `0010_product_barcode_images`. Rendering is dependency-free and shared
      by seed/demo generation and runtime creation — no new pip dependency.
      Existing valid EAN-13 Products receive images during idempotent demo
      seeding without replacing any existing Product fields.
    - New `GET /api/products/{product_id}/barcode-image`: VIEW-gated,
      organization-masked 404 semantics, returns the persisted `image/png`
      bytes and never generates/writes on GET. Product Library displays the
      image and provides `Download PNG` plus `Open / print` links.
    - Asset Scan response is now the approved discriminated union
      `{"match_type":"emission_source"|"product","data":{...}}`.
      Resolution order is EmissionSource first, then Product; both queries
      are scoped to the selected facility's organization. The handler remains
      read-only. Product matches show Product reference details in the scan
      UI and do not incorrectly select a consumption emission source.
    - Theme supersedes item 12's purple palette: white canvas, pastel-green
      surfaces, dark-green controls, and a **light-sage sidebar**. Inter is
      the body/UI face; Fraunces is used for headings/brand figures. No old
      purple tokens remain. Checked key text/control combinations at WCAG AA
      or better (minimum checked ratio 5.71:1).
    - Contract updated in `Docs/api-contract.md`; no RBAC/matrix changes.
      Migration passed both existing-DB upgrade and blank replay. Real local
      UI walkthrough covered sign-in, Dashboard, Overview, Reports,
      Consumption, Products, and Members. A blank-barcode Product received
      `2000000000060`, displayed its PNG, and exposed download/print links.
      Its actual persisted PNG round-tripped through the live non-mock Asset
      Scan API as `match_type: product`; a real source QR returned
      `match_type: emission_source`.
      Full backend suite: 249 passed (242 before); frontend
      `tsc -b --noEmit` and production build passed; oxlint passed with only
      the same pre-existing React advisory warnings.
16. **Demo Access panel configuration bug — diagnosed/fixed locally:**
    - Root cause was configuration placement, not React wiring. Commit
      `371b221` changed `frontend/.env.example` to
      `VITE_ENABLE_DEMO_ACCESS=true`, but Vite does not load `.env.example`;
      the key was absent from the loaded `frontend/.env.local`,
      so `import.meta.env.VITE_ENABLE_DEMO_ACCESS` was `undefined` and the
      correct `=== "true"` conditional remained false.
    - Added `VITE_ENABLE_DEMO_ACCESS=true` to local `.env.local` and restarted
      Vite cleanly. A temporary diagnostic log proved the runtime string was
      `true`; the log was removed immediately afterward. Real browser reload
      showed the panel, Owner/Admin filled `admin-demo@gmail.com`, and
      Employee filled `employee-demo@gmail.com`; both filled the shared demo
      password. Only the tracked environment file changed; no React/config
      source-code change was needed.
    - Production/Preview remains dashboard-configured: set the variable in
      the exact Vercel environment being viewed and redeploy. Committing
      `.env.example` alone never changes a Vercel build.
17. **Demo credential failure screenshot — investigated, not reproduced:**
    - Both public credentials (`admin-demo@gmail.com` and
      `employee-demo@gmail.com` with `DemoPass123!`) returned HTTP 200
      directly from the current local backend. A fresh real-browser Employee
      flow (click Demo Access button, then Sign In) also succeeded and landed
      authenticated as `employee-demo@gmail.com`; no UI/auth code change was
      needed.
    - Important deployment edge case: `seed_demo_data()` intentionally skips
      an existing user and therefore does not repair/reset that user's stored
      password hash. If a deployed database already contains either demo
      email with a different password, merely enabling
      `SEED_DEMO_ACCOUNTS=true` and redeploying will still leave that login at
      401. Confirm the frontend's actual API target first; any production hash
      reset must be deliberate rather than silently added to idempotent seed.

18. **Product scan -> consumption gap — diagnosed; superseded by item 19:**
    - `AssetScanCapture` invokes its selection callback only for
      `match_type: emission_source`; Product matches display reference data
      without selecting a consumption input or submitting a record.
    - `POST /consumption-records` and the DB require `emission_source_id`;
      calculations require `emission_factor_id`. Product reference fields
      are deliberately excluded by the current frozen contract. This is
      missing product-consumption functionality, not a failed scan/save.
    - Product `emissions_unit` is free text, with no structured consumption
      unit or source-type classification. Do not assume one scan means one
      consumed item, infer a scope from a barcode, or route Products through
      the generic RESOURCE/cement emission factor.
    - User requested implementation; contract/schema expansion still needs
      explicit approval under the existing governance rule. Proposed flow:
      scan selects Product -> user confirms quantity/date -> Log consumption;
      validated product factor/unit/classification, immutable historical
      snapshot, organization scoping, and downstream aggregation required.
      No implementation or contract changes made in this diagnostic pass.
    - Follow-up UI requirement: put quantity/date and `Log consumption`
      directly inside the `Product matched` card; it must save that Product
      and feed Dashboard totals, never the unrelated emission source below.
      Explicit confirmation of the proposed API/schema extension requested.

19. **Product matched-card consumption — implemented after explicit approval:**
    - User confirmed the API/schema extension including Product unit/scope
      configuration; specifically requested the `Log consumption` button
      inside `Product matched`, not in the unrelated source form below.
    - Branch `main`, starting HEAD `2a68c78` (that commit contained only the
      earlier diagnosis, not feature code). No git mutations performed.
    - `Docs/api-contract.md` updated first. Product create/update/read/scan
      shapes add nullable `consumption_unit` and `consumption_source_type`.
      Both are explicitly configured by OWNER/ADMIN or both null; enabled
      Products require exact `kg CO2e/{consumption_unit}` notation. Existing
      Products stay reference-only until configured; no backfill inference,
      no changes to existing values, no automatic consumption on scan.
    - `POST /consumption-records` accepts exactly one Product/source ID.
      Product quantities: positive Numeric(14,4), timezone-aware date,
      exact configured unit, Decimal half-up result to 4 places. Overflow,
      unconfigured Products and wrong units return documented 422 errors.
      All roles can log (ENTRY); Product/facility must share an organization.
      Cross-organization and inaccessible selections use masked 404.
    - Migration `0011_product_consumption`: Product configuration columns,
      nullable source/factor IDs, Product link + immutable JSON snapshot,
      historical source type, CHECK and composite tenant FK constraints.
      Product deletion nulls its live link, preserving snapshot + calculations.
      Downgrade refuses to erase existing Product consumption history.
    - Business logic: `backend/app/services/product_configuration.py`,
      `product_consumption.py`; shared `services/reports.py` aggregates both
      kinds for Dashboard, GraphQL Overview, and new reports. Existing saved
      reports remain snapshots. Existing WebSocket event carries the expanded
      record. No new GraphQL fields, emission categories or dependencies.
    - Frontend: `ProductConsumptionForm.tsx` inside `AssetScanCapture`;
      quantity defaults visibly to 1, editable date/time, explicit submit,
      success + Dashboard link, in-flight/after-success click lock, inline
      errors. Scanning works without any facility emission sources. Recent
      records show snapshot Product names. Source form remains independent.
      `ProductLibraryPage` adds role-gated configuration controls; shared
      scope labels reused. API types/mock adapter and scoped spacing updated.
    - Verification: existing backend suite 249 passed on migrated development
      DB; 25 new tests passed on isolated blank-migrated DB; final full suite
      274 passed (existing dependency deprecations/transaction warnings).
      Actual generated PNG -> scan (no write) -> explicit Product POST ->
      list/REST summary/GraphQL/report tested: 2 x 1.250000 = 2.5000 kg CO2e,
      displayed aggregate 2.50. History survives edit/disable/delete; tenant
      FK, roles, units, rounding, overflow and live event tested.
    - Frontend production build and typecheck passed; lint has the same 13
      existing advisory warnings, no errors. Seven Playwright browser cases
      cover matched-card save, Dashboard, no-source facility, unconfigured
      Product, retry, source logging, mock parity and OWNER configuration.
      Browser uses simulated camera/API responses; physical webcam and
      production deployment not exercised. Screenshots inspected for card
      layout and Dashboard 2.50 total. Initial harness intercept/readiness/
      click synchronization issues corrected; temporary event tracing removed.
    - Local migration applied; report worker restarted only after confirming
      it was idle. Real-mode Vite started on 127.0.0.1:5173; .env.local unchanged.
      Local frontend returns 200 and backend /health reports ok. No deployment.
    - Retained isolated verification database
      `carbon_product_consumption_verify_20260903` (reference seed + rollback-
      scoped tests); no development DB reset, DROP, or volume removal.

## Open items / not yet done (as of this handoff)

- No delete endpoints exist anywhere in this app except
  `DELETE /api/products/{id}` and the new membership
  `DELETE .../members/{user_id}` — organizations, facilities, emission
  sources, reports, and consumption records still have no delete endpoint
  at all. This has been flagged and deliberately left out of scope
  multiple times — do not assume they exist.
- A leftover manually-created test `Product` ("Verification Aluminium
  Bottle — Edited") may still be sitting in the dev database — a browser
  permission block prevented its cleanup during Product Library
  verification. Harmless, just noise; delete via Products page whenever
  convenient. Similarly, a disposable verification organization/accounts
  from the membership-management walkthrough (item 13) is also sitting in
  the local dev database.
- Pre-existing, unrelated `alembic check` drift between the `users` model
  and its migration around the `email` column — flagged during item 13's
  verification but not caused by it and not fixed. Worth a dedicated look
  at some point, not urgent.
- Audit logging has backend persistence/middleware/read endpoint/tests but
  no frontend API client method, page, or navigation. Treat it as a
  partially implemented user-facing feature, not end-to-end UI coverage.
- **Superseded by item 15:** Product scanning is now part of Asset Scan via
  the approved discriminated response contract; EmissionSource retains
  priority and both lookup branches are organization-scoped.
- Last-used organization auto-selection is not implemented. A proposal is
  pending human review; do not change login/session contracts before
  approval.
- Repo-wide CRLF/LF line-ending churn (see Git rules above) remains
  unfixed — cosmetic/diff-noise only, not a functional bug, not
  prioritized. One more file added to the known list:
  `backend/app/models/organization_member.py` (confirmed no semantic
  diff, matches the existing pattern).
- `prompt_granular_entry.txt`-style work (new emission-source categories
  beyond ENERGY/FUEL/RESOURCE, requiring proposed+cited emission factors;
  optional richer fields on consumption records like notes/equipment-id/
  cost) was drafted and handed off but not confirmed started/completed as
  of this handoff — check before assuming it's done or not started.
