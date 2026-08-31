"""Role-based authorization across REST, GraphQL, and WebSockets."""

import pytest

from app.authorization import (
    OrganizationAction,
    has_organization_access,
    role_allows,
)
from app.models.organization_member import (
    ROLE_ADMIN,
    ROLE_EMPLOYEE,
    ROLE_OWNER,
    VALID_ROLES,
)


def _owner_tree(client):
    organization = client.post(
        "/api/organizations",
        json={"name": "RBAC Organization", "industry_type": "manufacturing"},
    ).json()
    facility = client.post(
        "/api/facilities",
        json={
            "organization_id": organization["id"],
            "name": "RBAC Facility",
            "location": "Chennai, TN",
            "facility_type": "factory",
        },
    ).json()
    source = client.post(
        "/api/emission-sources",
        json={
            "facility_id": facility["id"],
            "source_type": "ENERGY",
            "source_name": "Grid electricity",
            "unit_of_measurement": "kWh",
            "barcode_value": "RBAC-SOURCE-001",
        },
    ).json()
    report_response = client.post(
        "/api/reports/generate",
        json={
            "organization_id": organization["id"],
            "report_period_start": "2026-08-01",
            "report_period_end": "2026-08-31",
        },
    )
    assert report_response.status_code == 201, report_response.text
    return organization, facility, source, report_response.json()


def _consumption_body(facility_id: int, source_id: int) -> dict:
    return {
        "emission_source_id": source_id,
        "facility_id": facility_id,
        "quantity_consumed": "10",
        "unit": "kWh",
        "recorded_at": "2026-08-20T00:00:00Z",
    }


class TestRoleMatrix:
    def test_valid_roles_are_exactly_the_three_supported_values(self):
        assert VALID_ROLES == frozenset({ROLE_OWNER, ROLE_ADMIN, ROLE_EMPLOYEE})

    @pytest.mark.parametrize("role", [ROLE_OWNER, ROLE_ADMIN])
    @pytest.mark.parametrize("action", list(OrganizationAction))
    def test_owner_and_admin_allow_every_action(self, role, action):
        assert role_allows(role, action)

    @pytest.mark.parametrize(
        ("action", "expected"),
        [
            (OrganizationAction.VIEW, True),
            (OrganizationAction.ENTRY, True),
            (OrganizationAction.WRITE, False),
        ],
    )
    def test_employee_is_view_plus_entry_only(self, action, expected):
        assert role_allows(ROLE_EMPLOYEE, action) is expected


class TestEmployeeAccess:
    def test_employee_can_view_every_surface_and_create_consumption(
        self, client, other_client, other_user, grant_membership
    ):
        organization, facility, source, report = _owner_tree(client)
        grant_membership(other_user.id, organization["id"], ROLE_EMPLOYEE)

        organization_response = other_client.get(
            f"/api/organizations/{organization['id']}"
        )
        assert organization_response.status_code == 200
        assert organization_response.json()["role"] == ROLE_EMPLOYEE
        assert other_client.get("/api/organizations").json()[0]["role"] == ROLE_EMPLOYEE
        assert (
            other_client.get(
                f"/api/facilities?organization_id={organization['id']}"
            ).status_code
            == 200
        )
        assert (
            other_client.get(
                f"/api/emission-sources?facility_id={facility['id']}"
            ).status_code
            == 200
        )
        assert (
            other_client.get(
                f"/api/consumption-records?facility_id={facility['id']}"
            ).status_code
            == 200
        )
        assert (
            other_client.get(
                f"/api/facilities/{facility['id']}/emissions-summary",
                params={"start_date": "2026-08-01", "end_date": "2026-08-31"},
            ).status_code
            == 200
        )
        assert other_client.get(f"/api/reports/{report['id']}").status_code == 200
        assert (
            other_client.get(
                f"/api/reports?organization_id={organization['id']}"
            ).status_code
            == 200
        )

        graphql_response = other_client.post(
            "/graphql",
            json={
                "query": "query Q($id: Int!) { organization(id: $id) { id name } }",
                "variables": {"id": organization["id"]},
            },
        )
        assert graphql_response.status_code == 200
        assert graphql_response.json()["data"]["organization"]["id"] == organization["id"]

        token = other_client.headers["Authorization"].split(" ", 1)[1]
        with other_client.websocket_connect(
            f"/ws/facilities/{facility['id']}?token={token}"
        ):
            pass
        with other_client.websocket_connect(
            f"/ws/organizations/{organization['id']}?token={token}"
        ):
            pass

        # Asset scan is explicitly classified as VIEW even though its HTTP
        # method is POST. Invalid image bytes reach validation (422), proving
        # role authorization did not mask the facility as a 404.
        scan = other_client.post(
            f"/api/facilities/{facility['id']}/asset-scan",
            files={"image": ("frame.jpg", b"not-an-image", "image/jpeg")},
        )
        assert scan.status_code == 422

        entry = other_client.post(
            "/api/consumption-records",
            json=_consumption_body(facility["id"], source["id"]),
        )
        assert entry.status_code == 201, entry.text

    def test_employee_write_denials_are_masked_as_not_found(
        self,
        client,
        other_client,
        other_user,
        grant_membership,
        db_session,
    ):
        organization, facility, _, _ = _owner_tree(client)
        grant_membership(other_user.id, organization["id"], ROLE_EMPLOYEE)

        # An unclassified future call defaults to the restrictive WRITE tier.
        assert not has_organization_access(
            db_session, other_user.id, organization["id"]
        )

        create_facility = other_client.post(
            "/api/facilities",
            json={
                "organization_id": organization["id"],
                "name": "Forbidden Facility",
                "location": "Nowhere",
                "facility_type": "factory",
            },
        )
        create_source = other_client.post(
            "/api/emission-sources",
            json={
                "facility_id": facility["id"],
                "source_type": "FUEL",
                "source_name": "Forbidden Source",
                "unit_of_measurement": "litre",
            },
        )
        generate_report = other_client.post(
            "/api/reports/generate",
            json={
                "organization_id": organization["id"],
                "report_period_start": "2026-08-01",
                "report_period_end": "2026-08-31",
            },
        )

        for response in (create_facility, create_source, generate_report):
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "NOT_FOUND"

        # Same shape as a genuine miss/non-membership, preserving the BOLA
        # masking convention rather than introducing a role-specific 403.
        absent = other_client.post(
            "/api/facilities",
            json={
                "organization_id": 99999999,
                "name": "Absent Parent",
                "location": "Nowhere",
                "facility_type": "factory",
            },
        )
        assert absent.status_code == 404
        assert absent.json()["error"]["code"] == "NOT_FOUND"
        assert set(create_facility.json()["error"]) == set(absent.json()["error"])

    def test_employee_may_create_a_separate_organization_and_owns_it(
        self, client, other_client, other_user, grant_membership
    ):
        organization, _, _, _ = _owner_tree(client)
        grant_membership(other_user.id, organization["id"], ROLE_EMPLOYEE)

        created = other_client.post(
            "/api/organizations",
            json={"name": "Employee's Own Org", "industry_type": "logistics"},
        )
        assert created.status_code == 201
        assert created.json()["role"] == ROLE_OWNER
        assert (
            other_client.get(f"/api/organizations/{organization['id']}").json()["role"]
            == ROLE_EMPLOYEE
        )


class TestAdminAccess:
    def test_admin_matches_owner_for_every_existing_mutation(
        self, client, other_client, other_user, grant_membership
    ):
        organization = client.post(
            "/api/organizations",
            json={"name": "Admin Organization", "industry_type": "manufacturing"},
        ).json()
        grant_membership(other_user.id, organization["id"], ROLE_ADMIN)

        assert (
            other_client.get(f"/api/organizations/{organization['id']}").json()["role"]
            == ROLE_ADMIN
        )
        facility = other_client.post(
            "/api/facilities",
            json={
                "organization_id": organization["id"],
                "name": "Admin Facility",
                "location": "Mumbai, MH",
                "facility_type": "warehouse",
            },
        )
        assert facility.status_code == 201, facility.text

        source = other_client.post(
            "/api/emission-sources",
            json={
                "facility_id": facility.json()["id"],
                "source_type": "ENERGY",
                "source_name": "Admin Source",
                "unit_of_measurement": "kWh",
            },
        )
        assert source.status_code == 201, source.text

        entry = other_client.post(
            "/api/consumption-records",
            json=_consumption_body(facility.json()["id"], source.json()["id"]),
        )
        assert entry.status_code == 201, entry.text

        report = other_client.post(
            "/api/reports/generate",
            json={
                "organization_id": organization["id"],
                "report_period_start": "2026-08-01",
                "report_period_end": "2026-08-31",
            },
        )
        assert report.status_code == 201, report.text


class TestOwnerRegression:
    def test_owner_existing_mutations_remain_allowed(self, client):
        organization, facility, source, report = _owner_tree(client)
        assert organization["role"] == ROLE_OWNER
        assert facility["organization_id"] == organization["id"]
        assert source["facility_id"] == facility["id"]
        assert report["organization_id"] == organization["id"]
        assert (
            client.post(
                "/api/consumption-records",
                json=_consumption_body(facility["id"], source["id"]),
            ).status_code
            == 201
        )
