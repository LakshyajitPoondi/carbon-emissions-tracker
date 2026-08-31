"""End-to-end API coverage for organization membership lifecycle."""

from app.models.organization_join_request import (
    JOIN_STATUS_APPROVED,
    JOIN_STATUS_PENDING,
    JOIN_STATUS_REJECTED,
    OrganizationJoinRequest,
)
from app.models.organization_member import (
    ROLE_ADMIN,
    ROLE_EMPLOYEE,
    ROLE_OWNER,
    OrganizationMember,
)


def _organization_and_code(client):
    organization = client.post(
        "/api/organizations",
        json={"name": "Membership Co", "industry_type": "manufacturing"},
    ).json()
    code_response = client.get(
        f"/api/organizations/{organization['id']}/join-code"
    )
    assert code_response.status_code == 200, code_response.text
    return organization, code_response.json()["join_code"]


def _submit(other_client, code):
    return other_client.post("/api/join-requests", json={"join_code": code})


class TestJoinRequestSubmission:
    def test_valid_code_creates_pending_request_and_is_visible_after_reload(
        self, client, other_client
    ):
        organization, code = _organization_and_code(client)

        response = _submit(other_client, code.lower())

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["organization_id"] == organization["id"]
        assert body["organization_name"] == organization["name"]
        assert body["status"] == JOIN_STATUS_PENDING
        assert body["decided_at"] is None
        assert body["decided_by"] is None
        assert other_client.get("/api/join-requests/me").json() == [body]

    def test_duplicate_pending_request_is_rejected(self, client, other_client):
        _, code = _organization_and_code(client)
        assert _submit(other_client, code).status_code == 201

        duplicate = _submit(other_client, code)

        assert duplicate.status_code == 422
        assert duplicate.json()["error"]["code"] == "JOIN_REQUEST_ALREADY_PENDING"

    def test_unknown_and_malformed_codes_share_the_masked_404(
        self, client, other_client
    ):
        _organization_and_code(client)

        unknown = _submit(
            other_client, "ORG-0000-0000-0000-0000-0000-0000"
        )
        malformed = _submit(other_client, "not a code")

        assert unknown.status_code == malformed.status_code == 404
        assert unknown.json() == malformed.json()
        assert unknown.json()["error"]["code"] == "NOT_FOUND"

    def test_regeneration_invalidates_old_code(self, client, other_client):
        organization, old_code = _organization_and_code(client)
        regenerated = client.post(
            f"/api/organizations/{organization['id']}/join-code/regenerate"
        )
        assert regenerated.status_code == 200, regenerated.text
        new_code = regenerated.json()["join_code"]
        assert new_code != old_code
        assert _submit(other_client, old_code).status_code == 404
        assert _submit(other_client, new_code).status_code == 201


class TestJoinRequestDecisions:
    def test_approval_creates_membership_with_approver_selected_role(
        self, client, other_client, other_user, db_session
    ):
        organization, code = _organization_and_code(client)
        request = _submit(other_client, code).json()

        approved = client.post(
            f"/api/organizations/{organization['id']}/join-requests/{request['id']}/approve",
            json={"role": ROLE_EMPLOYEE},
        )

        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == JOIN_STATUS_APPROVED
        membership = (
            db_session.query(OrganizationMember)
            .filter(
                OrganizationMember.user_id == other_user.id,
                OrganizationMember.organization_id == organization["id"],
            )
            .one()
        )
        assert membership.role == ROLE_EMPLOYEE
        assert other_client.get("/api/join-requests/me").json() == []
        assert (
            other_client.get(f"/api/organizations/{organization['id']}").json()[
                "role"
            ]
            == ROLE_EMPLOYEE
        )

    def test_rejection_creates_no_membership(
        self, client, other_client, other_user, db_session
    ):
        organization, code = _organization_and_code(client)
        request = _submit(other_client, code).json()

        rejected = client.post(
            f"/api/organizations/{organization['id']}/join-requests/{request['id']}/reject"
        )

        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["status"] == JOIN_STATUS_REJECTED
        assert (
            db_session.query(OrganizationMember)
            .filter(
                OrganizationMember.user_id == other_user.id,
                OrganizationMember.organization_id == organization["id"],
            )
            .first()
            is None
        )
        assert other_client.get(f"/api/organizations/{organization['id']}").status_code == 404


class TestMemberManagement:
    def test_employee_can_list_members_but_management_is_masked(
        self, client, other_client, other_user, grant_membership
    ):
        organization, _ = _organization_and_code(client)
        grant_membership(other_user.id, organization["id"], ROLE_EMPLOYEE)

        members = other_client.get(
            f"/api/organizations/{organization['id']}/members"
        )
        assert members.status_code == 200
        assert {member["role"] for member in members.json()} == {
            ROLE_OWNER,
            ROLE_EMPLOYEE,
        }

        denied = [
            other_client.get(
                f"/api/organizations/{organization['id']}/join-code"
            ),
            other_client.get(
                f"/api/organizations/{organization['id']}/join-requests"
            ),
            other_client.patch(
                f"/api/organizations/{organization['id']}/members/{other_user.id}",
                json={"role": ROLE_ADMIN},
            ),
            other_client.delete(
                f"/api/organizations/{organization['id']}/members/{other_user.id}"
            ),
        ]
        for response in denied:
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_last_owner_cannot_be_demoted_or_removed(self, client, current_user):
        organization, _ = _organization_and_code(client)
        member_url = (
            f"/api/organizations/{organization['id']}/members/{current_user.id}"
        )

        demote = client.patch(member_url, json={"role": ROLE_ADMIN})
        remove = client.delete(member_url)

        for response in (demote, remove):
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "LAST_OWNER_REQUIRED"

    def test_role_change_and_removal_take_effect(
        self, client, other_client, other_user, grant_membership
    ):
        organization, _ = _organization_and_code(client)
        grant_membership(other_user.id, organization["id"], ROLE_EMPLOYEE)
        member_url = (
            f"/api/organizations/{organization['id']}/members/{other_user.id}"
        )

        promoted = client.patch(member_url, json={"role": ROLE_ADMIN})
        assert promoted.status_code == 200
        assert promoted.json()["role"] == ROLE_ADMIN
        assert other_client.get(
            f"/api/organizations/{organization['id']}/join-code"
        ).status_code == 200

        removed = client.delete(member_url)
        assert removed.status_code == 204
        assert removed.content == b""
        assert other_client.get(f"/api/organizations/{organization['id']}").status_code == 404

    def test_self_removal_is_allowed_when_another_owner_remains(
        self, client, other_user, current_user, grant_membership
    ):
        organization, _ = _organization_and_code(client)
        grant_membership(other_user.id, organization["id"], ROLE_OWNER)

        response = client.delete(
            f"/api/organizations/{organization['id']}/members/{current_user.id}"
        )

        assert response.status_code == 204
        assert client.get(f"/api/organizations/{organization['id']}").status_code == 404

