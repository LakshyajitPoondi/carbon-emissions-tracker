"""Acceptance suite for object-level authorization (the BOLA fix).

Before this change, authentication was the only gate: a valid token let any
registered user read and write every other user's organizations, facilities,
sources, records, reports, audit log, GraphQL data and WebSocket streams.
These tests are the proof that each of those doors is now scoped to
membership, and they are written to fail loudly if any one of them is
reopened.

The whole suite turns on `other_client` (see conftest.py): a second
authenticated user with no membership anywhere. Without it, "unauthorized"
can only be expressed as "unauthenticated", which is a different — and
already fixed — bug.
"""

import pytest
from sqlalchemy.exc import IntegrityError, DBAPIError
from starlette.websockets import WebSocketDisconnect

from app.models.organization import Organization
from app.models.organization_member import ROLE_OWNER, OrganizationMember


# ---------------------------------------------------------------------------
# Helpers — build a full resource tree owned by `client`.
# ---------------------------------------------------------------------------


def _org(client, name="Tenant A Org"):
    r = client.post(
        "/api/organizations", json={"name": name, "industry_type": "manufacturing"}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _facility(client, organization_id, name="Tenant A Plant"):
    r = client.post(
        "/api/facilities",
        json={
            "organization_id": organization_id,
            "name": name,
            "location": "Chennai, TN",
            "facility_type": "factory",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _source(client, facility_id, barcode="ENSRC-AUTHZ-1"):
    r = client.post(
        "/api/emission-sources",
        json={
            "facility_id": facility_id,
            "source_type": "ENERGY",
            "source_name": "Grid electricity",
            "unit_of_measurement": "kWh",
            "barcode_value": barcode,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _token(test_client, email, password):
    r = test_client.post(
        "/api/auth/token", data={"username": email, "password": password}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture()
def tree(client):
    """An organization, facility and emission source, all owned by `client`."""
    organization = _org(client)
    facility = _facility(client, organization["id"])
    source = _source(client, facility["id"])
    return {"organization": organization, "facility": facility, "source": source}


# ---------------------------------------------------------------------------
# Membership creation
# ---------------------------------------------------------------------------


class TestMembershipCreation:
    def test_creating_an_organization_grants_owner_membership(
        self, client, db_session, current_user
    ):
        """The success path of the org+membership pair: both rows exist, and
        the role is the explicit OWNER value rather than anything defaulted."""
        organization = _org(client)

        member = (
            db_session.query(OrganizationMember)
            .filter(
                OrganizationMember.organization_id == organization["id"],
                OrganizationMember.user_id == current_user.id,
            )
            .one()
        )
        assert member.role == ROLE_OWNER
        assert member.role == "OWNER"

    def test_registration_alone_grants_no_membership(self, other_client, other_user, db_session):
        """A fresh account belongs to nothing — it does not silently inherit
        access to any existing organization."""
        memberships = (
            db_session.query(OrganizationMember)
            .filter(OrganizationMember.user_id == other_user.id)
            .count()
        )
        assert memberships == 0

    def test_an_invalid_role_is_rejected_by_the_database(
        self, db_session, current_user, owned_organization
    ):
        """The CHECK constraint, not the application, is the thing that makes
        an invalid role unrepresentable — so a direct insert cannot create
        one either."""
        db_session.add(
            OrganizationMember(
                user_id=current_user.id,
                organization_id=owned_organization["id"],
                role="SUPERADMIN",
            )
        )
        with pytest.raises((IntegrityError, DBAPIError)):
            db_session.flush()
        db_session.rollback()

    def test_role_has_no_default_and_must_be_set_explicitly(
        self, db_session, current_user, owned_organization
    ):
        """No server default and no Python default: a code path that forgets
        the role fails on NOT NULL instead of inheriting an implied one."""
        db_session.add(
            OrganizationMember(
                user_id=current_user.id, organization_id=owned_organization["id"]
            )
        )
        with pytest.raises((IntegrityError, DBAPIError)):
            db_session.flush()
        db_session.rollback()

    def test_organization_and_membership_are_committed_together(
        self, client, db_session, monkeypatch
    ):
        """If the membership insert fails, the request fails and the caller
        gets no organization back.

        Scope note, so this reads honestly: the test suite wraps each test in
        a transaction that is rolled back, and the endpoint shares that very
        session, so a test cannot observe real commit boundaries from the
        outside. What is asserted here is the caller-visible half — a failed
        membership insert means no 201 and no organization id handed out —
        together with the success-path assertion above that both rows exist.
        The single-commit structure in create_organization is what ties them.
        """
        monkeypatch.setattr(
            "app.routers.organizations.ROLE_OWNER", "NOT_A_VALID_ROLE"
        )

        with pytest.raises((IntegrityError, DBAPIError)):
            client.post(
                "/api/organizations",
                json={"name": "Doomed Org", "industry_type": "manufacturing"},
            )

        db_session.rollback()
        assert (
            db_session.query(Organization)
            .filter(Organization.name == "Doomed Org")
            .first()
            is None
        )


# ---------------------------------------------------------------------------
# REST cross-tenant denial
# ---------------------------------------------------------------------------


class TestRestCrossTenantDenial:
    def test_cannot_read_another_tenants_organization(self, other_client, tree):
        r = other_client.get(f"/api/organizations/{tree['organization']['id']}")
        assert r.status_code == 404

    def test_cannot_list_another_tenants_facilities(self, other_client, tree):
        """404, not an empty list — an empty list would still confirm the
        organization id is real."""
        r = other_client.get(
            f"/api/facilities?organization_id={tree['organization']['id']}"
        )
        assert r.status_code == 404

    def test_cannot_create_a_facility_in_another_tenants_organization(
        self, other_client, tree
    ):
        r = other_client.post(
            "/api/facilities",
            json={
                "organization_id": tree["organization"]["id"],
                "name": "Intruder Plant",
                "location": "Nowhere",
                "facility_type": "factory",
            },
        )
        assert r.status_code == 404

    def test_cannot_list_another_tenants_emission_sources(self, other_client, tree):
        r = other_client.get(
            f"/api/emission-sources?facility_id={tree['facility']['id']}"
        )
        assert r.status_code == 404

    def test_cannot_create_an_emission_source_in_another_tenants_facility(
        self, other_client, tree
    ):
        r = other_client.post(
            "/api/emission-sources",
            json={
                "facility_id": tree["facility"]["id"],
                "source_type": "FUEL",
                "source_name": "Intruder generator",
                "unit_of_measurement": "litres",
            },
        )
        assert r.status_code == 404

    def test_cannot_read_another_tenants_emissions_summary(self, other_client, tree):
        r = other_client.get(
            f"/api/facilities/{tree['facility']['id']}/emissions-summary"
            "?start_date=2026-08-01&end_date=2026-08-31"
        )
        assert r.status_code == 404

    def test_cannot_list_another_tenants_consumption_records(self, other_client, tree):
        r = other_client.get(
            f"/api/consumption-records?facility_id={tree['facility']['id']}"
        )
        assert r.status_code == 404

    def test_cannot_write_a_consumption_record_into_another_tenants_facility(
        self, other_client, tree
    ):
        r = other_client.post(
            "/api/consumption-records",
            json={
                "emission_source_id": tree["source"]["id"],
                "facility_id": tree["facility"]["id"],
                "quantity_consumed": "1000",
                "unit": "kWh",
                "recorded_at": "2026-08-20T00:00:00Z",
            },
        )
        assert r.status_code == 404

    def test_cannot_generate_a_report_for_another_tenants_organization(
        self, other_client, tree
    ):
        r = other_client.post(
            "/api/reports/generate",
            json={
                "organization_id": tree["organization"]["id"],
                "report_period_start": "2026-08-01",
                "report_period_end": "2026-08-31",
            },
        )
        assert r.status_code == 404

    def test_cannot_read_another_tenants_report(self, client, other_client, tree):
        generated = client.post(
            "/api/reports/generate",
            json={
                "organization_id": tree["organization"]["id"],
                "report_period_start": "2026-08-01",
                "report_period_end": "2026-08-31",
            },
        )
        assert generated.status_code == 201, generated.text
        report_id = generated.json()["id"]

        assert client.get(f"/api/reports/{report_id}").status_code == 200
        assert other_client.get(f"/api/reports/{report_id}").status_code == 404

    def test_cannot_list_another_tenants_reports(self, other_client, tree):
        r = other_client.get(
            f"/api/reports?organization_id={tree['organization']['id']}"
        )
        assert r.status_code == 404

    def test_cannot_print_a_label_for_another_tenants_source(self, other_client, tree):
        r = other_client.get(
            f"/api/emission-sources/{tree['source']['id']}/label?preview=false"
        )
        assert r.status_code == 404

    def test_cannot_asset_scan_another_tenants_facility(self, other_client, tree):
        """A real (if meaningless) upload, so the handler actually runs.

        Sending no file at all would return 422 from request validation
        before the handler is reached — which reveals nothing about the
        facility, but also proves nothing about authorization. With a file
        attached, the membership check is the first thing the handler does,
        so the 404 lands before the image is ever decoded.
        """
        r = other_client.post(
            f"/api/facilities/{tree['facility']['id']}/asset-scan",
            files={"image": ("frame.png", b"not-really-a-png", "image/png")},
        )
        assert r.status_code == 404

    def test_emission_factors_stay_shared_reference_data(self, other_client):
        """Deliberately NOT tenant-scoped: published coefficients with no
        organization_id and no per-tenant meaning. Authenticated, not
        membership-gated."""
        r = other_client.get("/api/emission-factors")
        assert r.status_code == 200
        assert len(r.json()) > 0


# ---------------------------------------------------------------------------
# 404 masking
# ---------------------------------------------------------------------------


class TestAbsentAndInaccessibleAreIndistinguishable:
    def test_organization_bodies_are_identical(self, other_client, tree):
        """The whole point of choosing 404 over 403: an inaccessible id must
        be indistinguishable from an absent one, or the API becomes an
        enumeration oracle for every tenant in the system."""
        inaccessible = other_client.get(
            f"/api/organizations/{tree['organization']['id']}"
        )
        absent = other_client.get("/api/organizations/99999999")

        assert inaccessible.status_code == absent.status_code == 404
        assert inaccessible.json()["error"]["code"] == absent.json()["error"]["code"]
        # Only the id differs; the shape, code and wording are the same.
        assert inaccessible.json()["error"]["message"] == (
            f"Organization {tree['organization']['id']} does not exist"
        )
        assert absent.json()["error"]["message"] == (
            "Organization 99999999 does not exist"
        )

    def test_facility_bodies_are_identical(self, other_client, tree):
        inaccessible = other_client.get(
            f"/api/emission-sources?facility_id={tree['facility']['id']}"
        )
        absent = other_client.get("/api/emission-sources?facility_id=99999999")

        assert inaccessible.status_code == absent.status_code == 404
        assert inaccessible.json()["error"]["code"] == absent.json()["error"]["code"]


# ---------------------------------------------------------------------------
# Positive: access follows membership, not creation
# ---------------------------------------------------------------------------


class TestSharedMembershipGrantsAccess:
    def test_a_directly_inserted_membership_grants_full_access(
        self, other_client, other_user, tree, grant_membership
    ):
        """Access is granted by the membership row itself, not by some
        incidental property of having created the organization.

        The membership is inserted directly because there is deliberately no
        API for adding a member yet — this proves the authorization layer is
        ready for one.
        """
        organization_id = tree["organization"]["id"]

        # Denied beforehand...
        assert other_client.get(f"/api/organizations/{organization_id}").status_code == 404

        grant_membership(other_user.id, organization_id)

        # ...and allowed afterwards, across the whole resource tree.
        assert other_client.get(f"/api/organizations/{organization_id}").status_code == 200
        assert (
            other_client.get(
                f"/api/facilities?organization_id={organization_id}"
            ).status_code
            == 200
        )
        assert (
            other_client.get(
                f"/api/emission-sources?facility_id={tree['facility']['id']}"
            ).status_code
            == 200
        )
        assert (
            other_client.get(
                f"/api/emission-sources/{tree['source']['id']}/label?preview=false"
            ).status_code
            == 200
        )


# ---------------------------------------------------------------------------
# GraphQL
# ---------------------------------------------------------------------------


class TestGraphQLScoping:
    def test_graphiql_console_is_still_public(self, client):
        """The authorization work must not re-break the GraphiQL page: the
        GET that serves the console HTML carries no token, because a browser
        address bar cannot send one."""
        del client.headers["Authorization"]
        r = client.get("/graphql")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")

    def test_graphql_queries_still_require_authentication(self, client):
        del client.headers["Authorization"]
        r = client.post("/graphql", json={"query": "{ __typename }"})
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "UNAUTHORIZED"

    def test_owner_can_query_their_own_organization(self, client, tree):
        r = client.post(
            "/graphql",
            json={
                "query": "query Q($id: Int!) { organization(id: $id) { name facilities { id } } }",
                "variables": {"id": tree["organization"]["id"]},
            },
        )
        assert r.status_code == 200
        assert r.json()["data"]["organization"]["name"] == "Tenant A Org"

    def test_graphql_is_not_a_second_unscoped_door(self, other_client, tree):
        """The same organization, denied through GraphQL exactly as it is
        through REST — and reported as NOT_FOUND, so GraphQL does not leak
        existence that the REST layer is careful to mask."""
        r = other_client.post(
            "/graphql",
            json={
                "query": "query Q($id: Int!) { organization(id: $id) { name facilities { id name } } }",
                "variables": {"id": tree["organization"]["id"]},
            },
        )
        assert r.status_code == 200  # transport-level success, per the contract
        body = r.json()
        assert body["data"]["organization"] is None
        assert body["errors"][0]["extensions"]["code"] == "NOT_FOUND"
        assert "Tenant A Org" not in r.text

    def test_root_query_fields_are_only_the_scoped_one(self):
        """A guard, not a behaviour test. Nested fields are safe because they
        are reachable only through organization(id), which is authorized. Add
        another root field and that reasoning silently stops holding — so this
        fails until the new field is scoped and listed here."""
        from app.graphql.schema import schema

        # Introspect the compiled graphql-core schema rather than parsing SDL
        # text, so the guard cannot be defeated by formatting.
        field_names = set(schema._schema.query_type.fields.keys())
        assert field_names == {"organization"}


# ---------------------------------------------------------------------------
# WebSockets
# ---------------------------------------------------------------------------


class TestWebSocketScoping:
    def test_non_member_cannot_join_a_facility_channel(self, other_client, tree):
        """Rejected before accept(), with the same close code as a facility
        that does not exist — a distinct 'forbidden' code would let anyone
        enumerate facility ids over the socket."""
        token = _token(other_client, "other-user@example.com", "other-pass-123")
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with other_client.websocket_connect(
                f"/ws/facilities/{tree['facility']['id']}?token={token}"
            ) as ws:
                ws.receive_text()
        assert exc_info.value.code == 4004

    def test_non_member_cannot_join_an_organization_channel(self, other_client, tree):
        token = _token(other_client, "other-user@example.com", "other-pass-123")
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with other_client.websocket_connect(
                f"/ws/organizations/{tree['organization']['id']}?token={token}"
            ) as ws:
                ws.receive_text()
        assert exc_info.value.code == 4004

    def test_member_can_still_join(self, client, tree):
        token = _token(client, "fixture-user@example.com", "fixture-pass-123")
        with client.websocket_connect(
            f"/ws/facilities/{tree['facility']['id']}?token={token}"
        ):
            pass


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


class TestAuditLogScoping:
    def test_a_user_sees_only_their_own_entries(self, client, other_client, tree):
        """`client` has just created an organization, facility and source —
        three audited writes. None of them belong to the other user."""
        mine = client.get("/api/audit-logs")
        theirs = other_client.get("/api/audit-logs")

        assert mine.status_code == theirs.status_code == 200
        assert len(mine.json()) >= 3
        assert theirs.json() == []

    def test_the_user_id_filter_cannot_widen_the_scope(
        self, client, other_client, current_user, tree
    ):
        """The mandatory predicate, proven. Asking for someone else's user_id
        returns nothing rather than their history: the caller's filter is
        ANDed onto `user_id == me`, never substituted for it."""
        assert len(client.get("/api/audit-logs").json()) >= 3

        # The other user asks, explicitly, for the first user's entries.
        r = other_client.get(f"/api/audit-logs?user_id={current_user.id}")
        assert r.status_code == 200
        assert r.json() == []

    def test_the_user_id_filter_still_narrows_within_your_own(
        self, client, current_user, tree
    ):
        r = client.get(f"/api/audit-logs?user_id={current_user.id}")
        assert r.status_code == 200
        assert len(r.json()) >= 3
        assert {entry["user_id"] for entry in r.json()} == {current_user.id}


# ---------------------------------------------------------------------------
# Source/facility tenant integrity
# ---------------------------------------------------------------------------


class TestSourceFacilityIntegrity:
    def test_api_rejects_a_source_from_a_different_facility(self, client, tree):
        """Both the source and the facility belong to this caller, so both
        membership checks pass — and the record is still refused, because the
        source does not belong to that facility."""
        other_facility = _facility(client, tree["organization"]["id"], name="Plant B")

        r = client.post(
            "/api/consumption-records",
            json={
                "emission_source_id": tree["source"]["id"],  # belongs to Plant A
                "facility_id": other_facility["id"],         # filed against Plant B
                "quantity_consumed": "1000",
                "unit": "kWh",
                "recorded_at": "2026-08-20T00:00:00Z",
            },
        )
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "SOURCE_FACILITY_MISMATCH"

    def test_database_rejects_the_same_pairing(self, client, db_session, tree):
        """The composite foreign key, independent of the handler. This is what
        protects every future write path — a script, a bulk import, a new
        endpoint — that forgets to repeat the API-level check."""
        from app.models.consumption_record import ConsumptionRecord

        other_facility = _facility(client, tree["organization"]["id"], name="Plant C")

        db_session.add(
            ConsumptionRecord(
                emission_source_id=tree["source"]["id"],
                facility_id=other_facility["id"],
                quantity_consumed="1000",
                unit="kWh",
                recorded_at="2026-08-20T00:00:00Z",
            )
        )
        with pytest.raises((IntegrityError, DBAPIError)):
            db_session.flush()
        db_session.rollback()
