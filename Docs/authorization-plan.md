# Authorization Plan — fixing the object-level access gap (BOLA)

**Status: proposal, awaiting review. No implementation code has been written.**

## 0. The problem, stated precisely

Authentication works: every endpoint except `POST /auth/register`,
`POST /auth/token`, `GET /health`, and `GET /graphql` (the console HTML)
rejects a missing or invalid bearer token with `401`. What is missing is the
next question — *whose data is this?*

There is currently no link of any kind between a `users` row and an
`organizations` row. The schema has no ownership column and no join table.
Every handler therefore answers "does this record exist?" and never "is this
record yours?". Any registered user can read and write every other user's
organizations, facilities, emission sources, consumption records, reports,
labels, asset scans, WebSocket streams, GraphQL data, and the global audit
log. The external finding is accurate, and it is exploitable with nothing
more than a fresh registration and an incrementing integer.

"Fixed" means: every path that reaches org-owned data — REST, GraphQL, and
WebSocket alike — resolves the requesting user to an organization membership
and refuses anything outside it.

---

## 1. Membership model decision

### Recommendation: `organization_members`, with one role today

```
organization_members
  id                 PK
  user_id            FK -> users.id            ON DELETE CASCADE
  organization_id    FK -> organizations.id    ON DELETE CASCADE
  role               VARCHAR(20) NOT NULL DEFAULT 'OWNER'
  created_at         TIMESTAMPTZ NOT NULL
  UNIQUE (user_id, organization_id)
  INDEX (organization_id)
```

### The alternative considered

`organizations.owner_user_id` — a single nullable-then-not-null FK column.
One column, one migration, and every check becomes
`org.owner_user_id == user.id`. It fully closes the vulnerability.

### Why the join table wins anyway

The honest comparison is not "simple vs complex" — both are one migration and
both produce exactly one helper function. The differences that matter:

- **Cost is nearly identical.** A membership table adds a model file and an
  `EXISTS` query. It does not add role logic, middleware, or policy
  engines. The `role` column exists but only ever holds `'OWNER'` in this
  round, and **no code branches on it**. That is the line between a
  foundation and over-engineering, and this plan stays on the near side of
  it.
- **`owner_user_id` makes sharing structurally impossible.** "Add my
  teammate to this organization" becomes a schema migration plus a rewrite
  of every check. With a membership row it is one `INSERT`. For a platform
  whose entire premise is *organizational* emissions tracking, a hard
  one-human-per-organization ceiling is a strange thing to bake into the
  schema.
- **It is the answer to the obvious follow-up question.** A reviewer looking
  at this fix will ask "so how do two people at the same company both use
  it?" The join table answers that without a second round of work.

I am not proposing `admin`/`editor`/`viewer`. There is one role, it is not
checked, and the field exists so that adding one later is a data change
rather than a migration. If you would rather have the smaller diff,
`owner_user_id` is a legitimate choice and everything else in this document
still applies — only the body of `is_member()` changes.

---

## 2. How a user becomes associated with an organization

**On registration: nothing.** `POST /auth/register` continues to create only
a user. A user with zero organizations is a valid state — they see empty
lists until they create or are added to one. Auto-creating a personal
organization at registration would mean inventing a name and would leave
junk orgs behind every login test.

**On organization creation: automatically, as `OWNER`.** `POST /organizations`
creates the organization *and* inserts the membership row for the calling
user, in a single transaction — if the membership insert fails, the
organization must not exist. This is the only way memberships are created in
this round, and it means the existing test suite mostly keeps working (see
§7).

**Adding other users: out of scope for this round, deliberately.** The table
supports it; no endpoint will expose it yet. The audit finding is about
unauthorized *access*, not about collaboration, and a member-invitation flow
brings its own questions (invite by email? does the invitee need to exist
first? can an owner remove themselves?) that are not worth answering under a
deadline.

If you want the minimal version anyway, it is one endpoint and I would scope
it tightly:

```
POST /organizations/{id}/members   { "email": "..." }   -> 201
  - caller must already be a member of {id}
  - target user must already exist (no invitations, no emails)
  - idempotent: re-adding an existing member returns the existing row
```

Say the word during review and I will fold it in; otherwise it stays out.

---

## 3. Scoping strategy

### The two access shapes

Everything reduces to one of these:

1. **Direct** — the resource carries `organization_id`, so check membership
   against it: `organizations`, `reports`.
2. **Walk-up** — the resource reaches an organization through foreign keys:
   - `facilities.organization_id` → org
   - `emission_sources.facility_id` → `facilities.organization_id` → org
   - `consumption_records.facility_id` → `facilities.organization_id` → org
   - `emission_calculations.consumption_record_id` → record → facility → org

### Proposed helpers

Plain functions in `app/authorization.py`, not FastAPI dependencies. They
return the loaded object so the handler does not re-query it, and — the
deciding reason — the same functions can be called from GraphQL resolvers
and the WebSocket handlers, which are not part of the REST dependency tree.

```python
is_member(db, user_id, organization_id) -> bool      # single EXISTS query

require_organization(db, user, organization_id) -> Organization
require_facility(db, user, facility_id) -> Facility
require_emission_source(db, user, emission_source_id) -> EmissionSource
require_report(db, user, report_id) -> Report
```

Each raises the same `404 NOT_FOUND` whether the row is absent or simply not
the caller's (see §8). Each is one indexed lookup plus one `EXISTS`; the
walk-up variants join to `facilities` rather than issuing two round trips.

### Every endpoint, and the check it needs

| Endpoint | Check |
| --- | --- |
| `POST /api/auth/register` | none — public |
| `POST /api/auth/token` | none — public |
| `GET /health` | none — public probe |
| `POST /api/organizations` | none to perform; **creates** the membership |
| `GET /api/organizations/{id}` | `require_organization(id)` |
| `POST /api/facilities` | `require_organization(body.organization_id)` |
| `GET /api/facilities?organization_id=` | `require_organization(organization_id)` |
| `POST /api/emission-sources` | `require_facility(body.facility_id)` |
| `GET /api/emission-sources?facility_id=` | `require_facility(facility_id)` |
| `GET /api/emission-sources/{id}/label` | `require_emission_source(id)` (→ facility → org) |
| `POST /api/facilities/{id}/asset-scan` | `require_facility(facility_id)` |
| `GET /api/facilities/{id}/emissions-summary` | `require_facility(facility_id)` |
| `POST /api/consumption-records` | `require_facility(body.facility_id)` **and** `require_emission_source(body.emission_source_id)` **and** the consistency check in §9 |
| `GET /api/consumption-records?facility_id=` | `require_facility(facility_id)` |
| `GET /api/emission-factors` | **none — see below** |
| `POST /api/reports/generate` | `require_organization(body.organization_id)` |
| `GET /api/reports/{id}` | `require_report(id)` (→ `report.organization_id`) |
| `GET /api/reports?organization_id=` | `require_organization(organization_id)` |
| `GET /api/audit-logs` | scope to caller — see below |
| `POST /graphql` | §4 |
| `WS /ws/facilities/{id}` | §5 |
| `WS /ws/organizations/{id}` | §5 |

**`emission_factors` is deliberately unscoped.** It is global reference data
— published emission coefficients per `(source_type, region)`, seeded by
`app/seed.py`, with no `organization_id` and no per-tenant meaning. Scoping
it would be miscategorising a lookup table as customer data. It stays behind
authentication (a token is still required) but not behind membership. This
is a decision, not an oversight, and I would document it as such in the
contract so it does not read as a missed endpoint.

**`emission_calculations` has no endpoint of its own.** It is only ever
serialized inside a consumption-record response, so it inherits that
record's check. No separate work, listed here for completeness.

### `GET /audit-logs` — the one that needs a decision

`audit_logs` has no `organization_id` column. Its rows record
`user_id`, `action`, `resource_type`, `resource_id`, `endpoint`,
`status_code`, `timestamp`. There is no reliable path from a row to an
organization: `resource_id` is null for every create-to-collection, and
`resource_type` is a derived string, not a foreign key.

Three options:

- **(a) Scope to the caller's own actions** — `WHERE user_id = current_user.id`.
  One line, no migration, closes the leak completely. Under the current
  one-member-per-organization reality this is *identical in content* to
  org-scoping. Loses the ability for an owner to audit a teammate, which is
  a capability that does not exist yet anyway.
- **(b) Add `organization_id` to `audit_logs`**, populated by the middleware.
  The "right" long-term shape, but the middleware derives its fields from the
  URL path and would need an extra database lookup per write to resolve the
  owning org — paying a query on every mutating request to enrich a log
  nobody currently reads per-org.
- **(c) Resolve org at read time** by joining `resource_type`/`resource_id`
  back to the owning tables. Fragile, and impossible for the many rows where
  `resource_id` is null.

**Recommendation: (a).** It is the smallest change that actually closes the
hole, and it is content-equivalent to (b) until organizations have more than
one member. Worth noting explicitly: rows with `user_id = NULL` — the
unauthenticated `401` attempts the middleware deliberately records — become
invisible to everyone under (a). That is an acceptable loss for now, but it
is the strongest argument for (b) later, and I would put that sentence in
the contract rather than let someone discover it.

---

## 4. GraphQL

GraphQL must not become a second, unscoped door to the same rows. Three
changes:

1. **Put the user in the context.** `get_graphql_context` currently builds
   `{db, emissions_loader, emission_sources_loader}` and has no idea who is
   asking. It gains `Depends(get_current_user)` and passes the user through.
   Note the interaction with the GraphiQL fix: the router-level dependency
   is `get_current_user_for_graphql`, which returns `None` on `GET` so the
   console HTML can load. The context getter must use the strict
   `get_current_user`, because the context is only ever built for an actual
   query execution — which is always a `POST`.

2. **Check in the root resolver.** `organization(id)` calls
   `require_organization(...)`. On failure it raises `GraphQLError` with
   `extensions.code = "NOT_FOUND"` — exactly the shape and wording the
   nonexistent-organization case already returns, so a denied organization
   is indistinguishable from an absent one, consistent with §8.

3. **Nested fields inherit, and that is sufficient — but verify it.**
   `facilities`, `emissionsSummary`, and `emissionSources` are only
   reachable *through* `organization(id)`. Once the root is authorized,
   every child is by construction within that organization, and the
   DataLoaders batch by `facility_id` values that came from the authorized
   organization. There is no `facility(id)` or `report(id)` root field
   today. **If one is ever added, it needs its own check** — I would add a
   test asserting the schema's root fields are exactly `{organization}` so
   that adding an unscoped root field fails CI rather than shipping.

---

## 5. WebSockets

Both endpoints already authenticate: the token arrives as a query parameter
(a browser WebSocket handshake cannot set headers), `get_user_from_token`
resolves it, and an invalid token closes with `CLOSE_UNAUTHORIZED`. They
then look up the facility/organization and close with `CLOSE_NOT_FOUND` if
it is absent — but they never ask whether the user is a member.

The fix slots into the existing sequence, **before `websocket.accept()`**, so
an unauthorized client is never added to the broadcast channel:

- `/ws/facilities/{facility_id}` — resolve the facility, then check
  membership of `facility.organization_id`.
- `/ws/organizations/{organization_id}` — check membership directly.

**Close code:** reuse `CLOSE_NOT_FOUND` rather than adding a "forbidden"
code, mirroring §8 — a non-member gets the same close code as someone
connecting to a channel that does not exist, so the socket cannot be used to
enumerate facility ids. The alternative (a distinct forbidden code) would
undo the masking that the REST layer is doing.

Broadcast fan-out itself needs no change: it is keyed by channel
(`facility:{id}`), and if only members can join a channel, only members
receive its messages.

---

## 6. Migration and existing dev data

**One new migration**, `0006_add_organization_members`: create the table,
its unique constraint, and the `organization_id` index.

**Existing organizations will have no members** and become permanently
unreachable — every check fails for every user. There is no correct
automatic backfill, because the information required (which user owns which
organization) was never recorded.

**Recommendation: reset, do not backfill.** `docker compose down -v` for the
local stack, then `alembic upgrade head` and re-seed. This is throwaway demo
data — a handful of organizations named "Acme Corp", "Audit Live Check",
"Label Demo Corp" and similar, created by my own verification runs. Writing
a backfill for it would be pure ceremony.

Two consequences worth stating rather than discovering:

- **`docker compose down -v` is a protected operation** under
  `agents/core.md` — it deletes the Postgres volume. I will not run it; it
  is yours to run, and this plan is where I ask for that approval.
- **The Kubernetes deployment has its own database** on the `postgres-data`
  PVC, entirely separate from the compose one. It needs the same treatment:
  `kubectl delete -f k8s/ && kubectl delete pvc postgres-data`, then
  redeploy. The migration runs automatically in the backend's `migrate` init
  container.
- **CI is unaffected.** It provisions a fresh Postgres service container per
  run and migrates from nothing, so it never sees legacy rows.

---

## 7. Test impact and the fixture pattern

### The estimate

111 test functions across 15 files (128 collected, after parametrization).

**The good news is structural:** the existing `client` fixture registers and
logs in as one user, and nearly every test creates its own organization
through that client. Once `POST /organizations` grants membership to the
caller, those tests are creating data they then own — and keep passing
untouched. The suite was accidentally written in a tenant-correct way.

Concretely, from grepping the suite:

- **~6 call sites break**, all for the same reason — hardcoded ids the
  fixture user does not own:
  - `test_auth.py:82,88` — `GET /api/organizations/1`
  - `test_security_headers.py:40,122` — `GET /api/organizations/1`
  - `test_audit_logs.py:129` — `GET /api/facilities?organization_id=1`
  - `test_audit_logs.py:284` — a `derive_resource` parametrize case using
    the path `/api/facilities/1/asset-scan` (unit-level, likely unaffected —
    listed for completeness)

  Several of these *want* a failure response and will now get `404` instead
  of `200`/`401`; each needs its expectation adjusted or its id replaced
  with an owned one.
- **`test_audit_logs.py` needs the most thought** (14 tests). Its assertions
  scope by `user_id` already, which survives; but any test reading rows it
  did not create needs revisiting under the §3(a) self-scoping rule.
- **New tests to add** — this is the real work, and the point of the
  exercise. Roughly 12–15 covering the negative path: a second user must be
  refused on every resource family (organization, facility, emission source,
  consumption record, report, label, asset scan, emissions summary, audit
  log), plus GraphQL and both WebSocket channels.

### The fixture pattern

Keep `client` exactly as it is, so the ~100 unaffected tests stay untouched.
Add three fixtures to `conftest.py`:

```python
@pytest.fixture()
def current_user(client, db_session) -> User:
    """The user `client` is authenticated as."""

@pytest.fixture()
def owned_organization(client) -> dict:
    """An organization created by — and therefore owned by — `client`."""

@pytest.fixture()
def other_client(db_session) -> TestClient:
    """A second authenticated client, as a DIFFERENT user with no
    membership in `owned_organization`. This is the fixture every
    authorization test is actually about."""
```

`other_client` is the important one: without it, "unauthorized" can only be
tested as "unauthenticated", which is the bug we already fixed. With it, each
negative test is two lines — take an id from `owned_organization`, assert
`other_client` gets `404`.

Note the constraint this must respect: `other_client` has to share the same
rollback-scoped connection as `db_session`, the way the existing `client`
fixture does, or its writes will not be visible to the test and will leak
into the shared dev database.

---

## 8. Error shape: 404, not 403

**Recommendation: return `404 NOT_FOUND` when a user requests a resource
they cannot access**, using the existing standard error shape and the
existing `NOT_FOUND` code, identical to a resource that genuinely does not
exist.

Reasoning:

- **`403` confirms existence.** `GET /api/organizations/57` returning
  `403 FORBIDDEN` tells an attacker organization 57 exists; `404` tells them
  nothing. With sequential integer ids and open registration, that
  distinction is the difference between "you cannot read the data" and "you
  cannot read the data but you can map the entire customer list, count
  tenants, and watch them grow." For a security fix specifically about
  object-level access, leaking the object graph through status codes
  undercuts the fix.
- **It requires no contract change for these paths.** Every affected
  endpoint already documents `404` with `NOT_FOUND`. Masking means the error
  surface does not grow, and the frontend needs no new branch.
- **The usual objection is debuggability** — "is it missing or am I not
  allowed?" That objection has real weight in a large multi-tenant system
  with a support team. It has very little here: one user per organization,
  and the answer is always "you are not a member."

Where `403` would be right, for the record: an endpoint where the caller
provably already knows the resource exists — for example a member-management
endpoint acting within an organization they belong to but lack the role for.
There is no such endpoint in this round, which is another reason `404`
uniformly is the simpler and safer rule.

`401` semantics do not change: no token or a bad token is still `401
UNAUTHORIZED`, before any membership check runs.

---

## 9. A related bug found while mapping this out

`POST /api/consumption-records` validates that `emission_source_id` exists
and that `facility_id` exists — but **never that the source belongs to that
facility.** Today that is a silent data-integrity bug: a record can attribute
one facility's consumption to another facility's source, and the emissions
calculation will happily proceed.

Under any authorization model it becomes a cross-tenant hole: with
`require_facility` and `require_emission_source` both passing individually,
a user who owns facility A could still post a record joining their facility
to *someone else's* source id — or, worse, write a record into their own
facility that references and reveals another tenant's source.

**Proposed fix, in the same round:** after both membership checks, assert
`source.facility_id == body.facility_id` and return `422` with a new code
`SOURCE_FACILITY_MISMATCH` if not. This is a contract addition (§10) and one
test.

---

## 10. Contract change request

Per `agents/core.md`, changes to `docs/api-contract.md` need approval before
implementation.

```
CONTRACT CHANGE REQUEST

Current contract:
  - Every endpoint requires a valid bearer token; no notion of ownership.
  - 404 NOT_FOUND documented as "resource does not exist".
  - GET /audit-logs returns all audit entries, filterable by user_id.
  - POST /consumption-records: 404 if source or facility absent; 422 if no
    matching emission factor.

Proposed contract:
  - New concept section: organization membership. POST /organizations makes
    the caller a member (role OWNER). Users with no membership see empty
    lists.
  - 404 NOT_FOUND redefined as "does not exist, or is not accessible to
    you" — deliberately indistinguishable, with the reasoning documented.
  - GET /audit-logs returns only the caller's own entries; the user_id
    filter narrows within that. Note that user_id=null rows (rejected
    unauthenticated attempts) are not visible to anyone.
  - GET /emission-factors documented as intentionally global reference data,
    authenticated but not membership-scoped.
  - POST /consumption-records: new 422 SOURCE_FACILITY_MISMATCH.
  - WebSocket: both channels close with the existing not-found close code
    for non-members.
  - GraphQL: organization(id) returns the existing NOT_FOUND GraphQL error
    for non-members.

Reason:
  Closes the object-level authorization (BOLA) finding: any authenticated
  user can currently read and write every other user's data through REST,
  GraphQL, and WebSockets.

Frontend impact:
  Low but nonzero. No request or response shape changes. The frontend
  already handles 404 on every affected call. Two behavioural notes:
  (1) a freshly registered user now has no organizations and the setup
  screen must cope with an empty state rather than assuming id 1 exists;
  (2) anything that hardcodes an organization id will now 404.

Breaking change: YES — for any client relying on cross-organization access,
which is precisely the behaviour being removed.
```

---

## 11. Proposed implementation order

Each step leaves the suite green, so review can happen at any boundary.

1. Migration `0006` + `OrganizationMember` model + `app/authorization.py`
   helpers, with unit tests for the helpers. No handler changes yet.
2. `POST /organizations` grants membership. Suite still green.
3. REST scoping, one router at a time: organizations → facilities →
   emission sources → consumption records → reports → labels/asset scan.
4. `GET /audit-logs` self-scoping.
5. GraphQL context + root resolver check + the root-fields guard test.
6. WebSocket membership checks on both channels.
7. `SOURCE_FACILITY_MISMATCH` (§9).
8. `conftest.py` fixtures + the negative-path test suite.
9. `docs/api-contract.md` update, once §10 is approved.

Rough size: one new model, one migration, one new module, edits to 7
routers, 2 GraphQL files, 1 WebSocket router, plus ~15 new tests and ~6
existing assertions adjusted.

---

## 12. Decisions I need from you before writing code

1. **Membership table or `owner_user_id`?** I recommend the table (§1).
2. **Member-invitation endpoint — in or out?** I recommend out (§2).
3. **Audit-log scoping: option (a) self-scoped?** I recommend yes (§3).
4. **404 masking rather than 403?** I recommend yes (§8).
5. **Approval to reset the dev databases** — `docker compose down -v` is
   yours to run, and the k8s PVC needs deleting too (§6).
6. **Contract change approval** (§10).
7. **Fix the source/facility mismatch bug in this round?** I recommend yes
   (§9); it is small and it is a real hole.
