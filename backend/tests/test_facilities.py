"""Tests for POST /api/facilities and the 404 case."""


class TestCreateFacility:
    def test_success(self, client):
        # Create parent organization first
        org_resp = client.post(
            "/api/organizations",
            json={"name": "Acme Corp", "industry_type": "manufacturing"},
        )
        org_id = org_resp.json()["id"]

        resp = client.post(
            "/api/facilities",
            json={
                "organization_id": org_id,
                "name": "Chennai Plant",
                "location": "Chennai, TN",
                "facility_type": "factory",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Chennai Plant"
        assert data["organization_id"] == org_id
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_nonexistent_organization_returns_404(self, client):
        resp = client.post(
            "/api/facilities",
            json={
                "organization_id": 99999,
                "name": "Ghost Plant",
                "location": "Nowhere",
                "facility_type": "warehouse",
            },
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"]["code"] == "NOT_FOUND"
        assert "99999" in data["error"]["message"]
