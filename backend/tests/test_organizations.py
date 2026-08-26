"""Tests for POST /api/organizations and GET /api/organizations/{id}."""


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

    def test_not_found(self, client):
        resp = client.get("/api/organizations/99999")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"]["code"] == "NOT_FOUND"
