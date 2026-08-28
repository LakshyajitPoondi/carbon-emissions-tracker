"""Security response headers (HSTS and companions).

Scope note, stated plainly because it matters for how much these tests are
worth: this file tests the *application* half of TLS support — the headers
the app sends, on every response, including error responses. It does not
and cannot test the TLS handshake itself. Whether uvicorn actually presents
a certificate on :8443, and whether a browser accepts it, is infrastructure
behaviour outside the ASGI app; TestClient never opens a socket. Those parts
are covered by the manual verification steps written up in the README and
docs/api-contract.md.

The headers are read from the environment on each request, so these tests
set env vars with monkeypatch rather than rebuilding the app.
"""

import pytest

from app.middleware.security_headers import build_hsts_header

HSTS = "Strict-Transport-Security"


class TestHSTSPresence:
    def test_present_on_a_successful_response(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.headers[HSTS] == "max-age=31536000; includeSubDomains"

    def test_present_on_an_authenticated_api_response(self, client):
        response = client.post(
            "/api/organizations",
            json={"name": "Secure Corp", "industry_type": "manufacturing"},
        )
        assert response.status_code == 201
        assert HSTS in response.headers

    def test_present_on_a_401(self, client):
        """The response an attacker sees most often still has to carry it."""
        client.headers.pop("Authorization")
        response = client.get("/api/organizations/1")
        assert response.status_code == 401
        assert HSTS in response.headers

    def test_present_on_a_404(self, client):
        response = client.get("/api/organizations/999999")
        assert response.status_code == 404
        assert HSTS in response.headers

    def test_present_on_a_422(self, client):
        response = client.post("/api/organizations", json={"name": ""})
        assert response.status_code == 422
        assert HSTS in response.headers

    def test_present_on_the_graphql_endpoint(self, client):
        response = client.post("/graphql", json={"query": "{__typename}"})
        assert HSTS in response.headers

    def test_sent_over_plain_http_too(self, client):
        """Deliberate: the header is not conditioned on the request scheme.

        TestClient speaks http, and the header is still sent — which is the
        behaviour production depends on, where a platform terminates TLS
        upstream and this app only ever sees plain HTTP. Browsers ignore
        HSTS received over http (RFC 6797), so this is inert rather than
        wrong when the request really was insecure."""
        response = client.get("/health")
        assert response.url.scheme == "http"
        assert HSTS in response.headers


class TestHSTSConfiguration:
    def test_defaults_to_one_year_with_subdomains_and_no_preload(self, client):
        value = client.get("/health").headers[HSTS]
        assert value == "max-age=31536000; includeSubDomains"
        assert "preload" not in value

    def test_max_age_is_configurable(self, client, monkeypatch):
        monkeypatch.setenv("HSTS_MAX_AGE", "600")
        assert client.get("/health").headers[HSTS] == "max-age=600; includeSubDomains"

    def test_include_subdomains_can_be_turned_off(self, client, monkeypatch):
        monkeypatch.setenv("HSTS_INCLUDE_SUBDOMAINS", "false")
        assert client.get("/health").headers[HSTS] == "max-age=31536000"

    def test_preload_can_be_opted_into(self, client, monkeypatch):
        monkeypatch.setenv("HSTS_PRELOAD", "true")
        value = client.get("/health").headers[HSTS]
        assert value == "max-age=31536000; includeSubDomains; preload"

    def test_can_be_disabled_entirely(self, client, monkeypatch):
        monkeypatch.setenv("HSTS_ENABLED", "false")
        assert HSTS not in client.get("/health").headers

    def test_zero_max_age_omits_the_header(self, client, monkeypatch):
        """max-age=0 means "forget this policy", which is a thing you might
        genuinely want to send — but as a config value here it reads as
        "off", and sending a bare max-age=0 by accident would silently
        release browsers from HTTPS."""
        monkeypatch.setenv("HSTS_MAX_AGE", "0")
        assert HSTS not in client.get("/health").headers

    @pytest.mark.parametrize("raw", ["not-a-number", ""])
    def test_unparseable_max_age_falls_back_to_the_default(self, monkeypatch, raw):
        monkeypatch.setenv("HSTS_MAX_AGE", raw)
        assert build_hsts_header() == "max-age=31536000; includeSubDomains"


class TestCompanionHeaders:
    @pytest.mark.parametrize(
        "header,expected",
        [
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
            ("Referrer-Policy", "no-referrer"),
        ],
    )
    def test_hardening_headers_are_present(self, client, header, expected):
        assert client.get("/health").headers[header] == expected

    def test_present_on_error_responses_as_well(self, client):
        client.headers.pop("Authorization")
        headers = client.get("/api/organizations/1").headers
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"


class TestExistingBehaviourUnaffected:
    def test_cors_headers_still_returned(self, client):
        """The security middleware wraps CORSMiddleware, so it must not
        shadow the CORS headers the browser needs."""
        response = client.get(
            "/health", headers={"Origin": "http://localhost:5173"}
        )
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert HSTS in response.headers
