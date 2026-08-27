"""Tests for POST /api/auth/register, POST /api/auth/token, and the
get_current_user protection applied to every other router."""


class TestRegister:
    def test_success(self, client):
        resp = client.post(
            "/api/auth/register",
            json={"email": "newuser@example.com", "password": "supersecret123"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "newuser@example.com"
        assert "id" in data
        assert "created_at" in data
        assert "password" not in data
        assert "hashed_password" not in data

    def test_duplicate_email_returns_422(self, client):
        client.post(
            "/api/auth/register",
            json={"email": "dupe@example.com", "password": "supersecret123"},
        )
        resp = client.post(
            "/api/auth/register",
            json={"email": "dupe@example.com", "password": "anotherpassword"},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"

    def test_short_password_returns_422(self, client):
        resp = client.post(
            "/api/auth/register",
            json={"email": "shortpass@example.com", "password": "short"},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


class TestLogin:
    def test_success(self, client):
        client.post(
            "/api/auth/register",
            json={"email": "loginuser@example.com", "password": "correcthorse123"},
        )
        resp = client.post(
            "/api/auth/token",
            data={"username": "loginuser@example.com", "password": "correcthorse123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["token_type"] == "bearer"
        assert isinstance(data["access_token"], str) and len(data["access_token"]) > 0

    def test_wrong_password_returns_401(self, client):
        client.post(
            "/api/auth/register",
            json={"email": "wrongpass@example.com", "password": "correcthorse123"},
        )
        resp = client.post(
            "/api/auth/token",
            data={"username": "wrongpass@example.com", "password": "notthecorrectpass"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"

    def test_nonexistent_user_returns_401(self, client):
        resp = client.post(
            "/api/auth/token",
            data={"username": "doesnotexist@example.com", "password": "whatever123"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


class TestProtectedEndpoints:
    """client already carries a valid token (see conftest.client); these
    tests remove/replace it to exercise the missing/invalid-token paths."""

    def test_request_without_token_returns_401(self, client):
        del client.headers["Authorization"]
        resp = client.get("/api/organizations/1")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"

    def test_request_with_invalid_token_returns_401(self, client):
        client.headers["Authorization"] = "Bearer not-a-real-token"
        resp = client.get("/api/organizations/1")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"

    def test_request_with_valid_token_passes_auth(self, client):
        # A valid token should clear the auth layer entirely and reach the
        # real route logic (a 404 here, not a 401).
        resp = client.get("/api/organizations/99999")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"
