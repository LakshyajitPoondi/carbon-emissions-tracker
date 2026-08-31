"""Tests for POST /api/organizations, GET /api/organizations and
GET /api/organizations/{id}."""


def _create(client, name, industry_type="manufacturing"):
    resp = client.post(
        "/api/organizations", json={"name": name, "industry_type": industry_type}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestCreateOrganization:
    def test_success(self, client):
        resp = client.post(
            "/api/organizations",
            json={"name": "Acme Manufacturing", "industry_type": "manufacturing"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Acme Manufacturing"
        assert data["industry_type"] == "manufacturing"
        assert data["role"] == "OWNER"
        assert "id" in data
        assert "created_at" in data
        # Contract: organization response has no updated_at
        assert "updated_at" not in data

    def test_missing_name_returns_422(self, client):
        resp = client.post(
            "/api/organizations",
            json={"industry_type": "manufacturing"},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"


class TestListOrganizations:
    """GET /api/organizations — the caller's memberships, not their creations.

    The distinction matters enough to be worth stating: a wrong
    implementation that filtered on "who created this" would pass every test
    here except test_includes_an_organization_joined_by_direct_membership,
    because the ordinary way to get an organization is to create it. That
    test is the one doing real work.
    """

    def test_returns_the_users_organizations_in_name_order(self, client):
        # Created out of alphabetical order on purpose.
        _create(client, "Zephyr Logistics")
        _create(client, "Acme Manufacturing")

        resp = client.get("/api/organizations")
        assert resp.status_code == 200

        body = resp.json()
        assert [org["name"] for org in body] == [
            "Acme Manufacturing",
            "Zephyr Logistics",
        ]
        # Same object shape as GET /organizations/{id}.
        assert set(body[0]) == {
            "id",
            "name",
            "industry_type",
            "created_at",
            "role",
        }
        assert {org["role"] for org in body} == {"OWNER"}

    def test_returns_empty_list_for_a_user_with_no_memberships(self, other_client):
        """A freshly registered account belongs to nothing — an empty list,
        not a 404 and not an error."""
        resp = other_client.get("/api/organizations")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_includes_an_organization_joined_by_direct_membership(
        self, client, other_client, other_user, grant_membership
    ):
        """The point of the endpoint.

        `other_user` did not create this organization and has never called an
        endpoint that touches it — the membership row is inserted directly by
        the fixture, which is the only way to distinguish a membership query
        from a creator query. Before the insert the list is empty; after it,
        the organization appears.
        """
        organization = _create(client, "Shared Industries")

        assert other_client.get("/api/organizations").json() == []

        grant_membership(other_user.id, organization["id"])

        body = other_client.get("/api/organizations").json()
        assert [org["name"] for org in body] == ["Shared Industries"]
        assert body[0]["id"] == organization["id"]
        assert body[0]["role"] == "OWNER"

    def test_one_users_organizations_never_appear_in_anothers(
        self, client, other_client
    ):
        mine = _create(client, "Mine Only")
        theirs_resp = other_client.post(
            "/api/organizations",
            json={"name": "Theirs Only", "industry_type": "logistics"},
        )
        assert theirs_resp.status_code == 201
        theirs = theirs_resp.json()

        my_list = client.get("/api/organizations").json()
        their_list = other_client.get("/api/organizations").json()

        assert [org["id"] for org in my_list] == [mine["id"]]
        assert [org["id"] for org in their_list] == [theirs["id"]]
        # Neither name leaks into the other's response.
        assert "Theirs Only" not in client.get("/api/organizations").text
        assert "Mine Only" not in other_client.get("/api/organizations").text

    def test_requires_authentication(self, client):
        """Asserted explicitly rather than assumed to be inherited from the
        router-level dependency."""
        del client.headers["Authorization"]
        resp = client.get("/api/organizations")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"


class TestGetOrganization:
    def test_success(self, client):
        # Create first
        create_resp = client.post(
            "/api/organizations",
            json={"name": "Test Org", "industry_type": "tech"},
        )
        org_id = create_resp.json()["id"]

        resp = client.get(f"/api/organizations/{org_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == org_id
        assert data["name"] == "Test Org"
        assert data["role"] == "OWNER"

    def test_not_found(self, client):
        resp = client.get("/api/organizations/99999")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"]["code"] == "NOT_FOUND"
