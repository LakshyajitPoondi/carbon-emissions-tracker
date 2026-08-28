"""Audit logging: the middleware's writes, and the read-back endpoint.

Two things make these tests look the way they do.

First, audit rows are written from a background task (see
app/middleware/audit.py). TestClient runs the full ASGI cycle, background
tasks included, before returning the response — so by the time a
`client.post(...)` call returns here, the audit row is already written and
can be asserted on synchronously. In production that write happens after
the client has its response; the ordering guarantee under TestClient is a
testing convenience, not a claim about request latency.

Second, assertions are scoped to the fixture user's own id rather than
counting the whole table. The dev database is shared, and any manual curl
against the running app leaves real audit rows behind; a test that asserts
"the table has 3 rows" would pass locally and fail the moment someone
clicks around the app. Each test registers a fresh user (rolled back
afterwards), so filtering by that user's id isolates the test's own rows.
"""

import pytest

from app.middleware.audit import derive_resource
from app.models.audit_log import AuditLog
from app.models.user import User


@pytest.fixture()
def current_user(client, db_session) -> User:
    """The user the `client` fixture registered and logged in as. Depends on
    `client` so registration has definitely happened first."""
    return db_session.query(User).filter(User.email == "fixture-user@example.com").one()


def _rows_for(db_session, user_id):
    return (
        db_session.query(AuditLog)
        .filter(AuditLog.user_id == user_id)
        .order_by(AuditLog.id)
        .all()
    )


def _create_organization(client, name="Audited Org"):
    response = client.post(
        "/api/organizations",
        json={"name": name, "industry_type": "manufacturing"},
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestWriteOperationsAreAudited:
    def test_post_organization_writes_a_matching_audit_row(
        self, client, db_session, current_user
    ):
        _create_organization(client)

        rows = _rows_for(db_session, current_user.id)
        assert len(rows) == 1

        row = rows[0]
        assert row.action == "CREATE"
        assert row.resource_type == "organization"
        assert row.endpoint == "/api/organizations"
        assert row.status_code == 201
        assert row.user_id == current_user.id
        # No id in the path of a POST-to-collection — documented limitation.
        assert row.resource_id is None
        assert row.timestamp is not None

    def test_each_write_gets_its_own_row(self, client, db_session, current_user):
        _create_organization(client, name="First Org")
        _create_organization(client, name="Second Org")

        rows = _rows_for(db_session, current_user.id)
        assert len(rows) == 2
        assert [row.action for row in rows] == ["CREATE", "CREATE"]

    def test_failed_write_is_audited_with_its_real_status_code(
        self, client, db_session, current_user
    ):
        """A rejected write is exactly the kind of thing an audit trail is
        for, so the 404 is logged, not dropped."""
        response = client.post(
            "/api/facilities",
            json={
                "organization_id": 999999,
                "name": "Ghost Plant",
                "location": "Nowhere",
                "facility_type": "factory",
            },
        )
        assert response.status_code == 404

        rows = _rows_for(db_session, current_user.id)
        assert len(rows) == 1
        assert rows[0].resource_type == "facility"
        assert rows[0].status_code == 404
        assert rows[0].action == "CREATE"

    def test_nested_path_records_the_sub_resource_and_the_id_in_the_path(
        self, client, db_session, current_user
    ):
        """POST /api/facilities/{id}/asset-scan — the id in the path is
        captured, and the sub-resource (not the parent collection) names the
        resource_type. Sent without the required image field, so it is
        rejected before the handler runs and needs no webcam frame or model;
        what matters here is the path parsing and that a rejection is still
        audited."""
        response = client.post("/api/facilities/42/asset-scan")
        assert response.status_code in (404, 422)

        rows = _rows_for(db_session, current_user.id)
        assert len(rows) == 1
        assert rows[0].resource_type == "asset_scan"
        assert rows[0].resource_id == 42
        assert rows[0].endpoint == "/api/facilities/42/asset-scan"
        assert rows[0].status_code == response.status_code


class TestReadOperationsAreNotAudited:
    def test_get_creates_no_audit_row(self, client, db_session, current_user):
        organization = _create_organization(client)
        rows_after_write = _rows_for(db_session, current_user.id)
        assert len(rows_after_write) == 1

        assert client.get(f"/api/organizations/{organization['id']}").status_code == 200
        assert client.get("/api/facilities?organization_id=1").status_code == 200
        assert client.get("/api/emission-factors").status_code == 200

        # Still exactly the one row from the POST.
        assert len(_rows_for(db_session, current_user.id)) == 1

    def test_register_and_login_are_not_audited(self, client, db_session):
        """The `client` fixture already POSTed to both /auth/register and
        /auth/token to get its token. Logging in is not a data mutation of
        the kind this trail records, so neither left a row."""
        auth_rows = (
            db_session.query(AuditLog)
            .filter(AuditLog.endpoint.in_(["/api/auth/register", "/api/auth/token"]))
            .all()
        )
        assert auth_rows == []


class TestUnauthenticatedWrites:
    def test_rejected_write_is_logged_with_a_null_user(self, client, db_session):
        """401s are logged too — with user_id NULL, since no user was ever
        resolved. Scoped by endpoint+status here because there is no user id
        to filter on."""
        endpoint = "/api/organizations"
        baseline = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.endpoint == endpoint,
                AuditLog.status_code == 401,
                AuditLog.user_id.is_(None),
            )
            .count()
        )

        client.headers.pop("Authorization")
        response = client.post(
            endpoint, json={"name": "Anon Org", "industry_type": "manufacturing"}
        )
        assert response.status_code == 401

        after = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.endpoint == endpoint,
                AuditLog.status_code == 401,
                AuditLog.user_id.is_(None),
            )
            .count()
        )
        assert after == baseline + 1


class TestListAuditLogsEndpoint:
    def test_returns_this_users_entries_most_recent_first(
        self, client, db_session, current_user
    ):
        _create_organization(client, name="Org One")
        _create_organization(client, name="Org Two")
        _create_organization(client, name="Org Three")

        response = client.get(f"/api/audit-logs?user_id={current_user.id}")
        assert response.status_code == 200, response.text

        body = response.json()
        assert len(body) == 3
        assert [entry["id"] for entry in body] == sorted(
            (entry["id"] for entry in body), reverse=True
        )
        assert {entry["user_id"] for entry in body} == {current_user.id}
        assert body[0]["action"] == "CREATE"
        assert body[0]["resource_type"] == "organization"
        assert body[0]["endpoint"] == "/api/organizations"
        assert body[0]["status_code"] == 201

    def test_filters_by_resource_type(self, client, db_session, current_user):
        _create_organization(client, name="Filterable Org")
        organization = _create_organization(client, name="Parent Org")
        facility_response = client.post(
            "/api/facilities",
            json={
                "organization_id": organization["id"],
                "name": "Chennai Plant",
                "location": "Chennai, TN",
                "facility_type": "factory",
            },
        )
        assert facility_response.status_code == 201, facility_response.text

        response = client.get(
            f"/api/audit-logs?user_id={current_user.id}&resource_type=facility"
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["resource_type"] == "facility"

        response = client.get(
            f"/api/audit-logs?user_id={current_user.id}&resource_type=organization"
        )
        assert len(response.json()) == 2

    def test_limit_and_offset_page_without_overlap(
        self, client, db_session, current_user
    ):
        for index in range(5):
            _create_organization(client, name=f"Paged Org {index}")

        base = f"/api/audit-logs?user_id={current_user.id}"
        first_page = client.get(f"{base}&limit=2").json()
        second_page = client.get(f"{base}&limit=2&offset=2").json()
        remainder = client.get(f"{base}&limit=2&offset=4").json()

        assert len(first_page) == 2
        assert len(second_page) == 2
        assert len(remainder) == 1

        ids = [entry["id"] for entry in first_page + second_page + remainder]
        assert len(set(ids)) == 5, "pages must not overlap or skip entries"
        assert ids == sorted(ids, reverse=True), "paging stays most-recent-first"

    def test_filters_by_user_id(self, client, db_session, current_user):
        _create_organization(client, name="Mine")

        other_user_id = current_user.id + 10_000
        response = client.get(f"/api/audit-logs?user_id={other_user_id}")
        assert response.status_code == 200
        assert response.json() == []

    def test_rejects_an_out_of_range_limit(self, client, current_user):
        assert client.get("/api/audit-logs?limit=0").status_code == 422
        assert client.get("/api/audit-logs?limit=500").status_code == 422

    def test_requires_authentication(self, client):
        client.headers.pop("Authorization")
        response = client.get("/api/audit-logs")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"


class TestResourceDerivation:
    """Unit coverage for the path-to-resource rules, including the two
    shapes the REST API has no write endpoint for yet (PATCH with an id,
    and a plain DELETE), so the rules stay pinned as endpoints are added."""

    @pytest.mark.parametrize(
        "path,expected",
        [
            ("/api/organizations", ("organization", None)),
            ("/api/facilities", ("facility", None)),
            ("/api/facilities/5", ("facility", 5)),
            ("/api/emission-sources", ("emission_source", None)),
            ("/api/consumption-records", ("consumption_record", None)),
            # Trailing verb: the collection it acts on wins, not "generate".
            ("/api/reports/generate", ("report", None)),
            # Sub-resource after an id: the sub-resource wins.
            ("/api/facilities/1/asset-scan", ("asset_scan", 1)),
            ("/api/organizations/3/reports", ("report", 3)),
            # Unprefixed and empty paths still produce something storable.
            ("/health", ("health", None)),
            ("/", ("unknown", None)),
        ],
    )
    def test_derives_resource_type_and_id(self, path, expected):
        assert derive_resource(path) == expected
