"""ZPL label generation — GET /api/emission-sources/{id}/label.

The preview renderer (Labelary) is an external HTTP service. No test here
makes a real network call: conftest.py sets LABEL_PREVIEW_ENABLED=false for
the whole suite, and the two tests that exercise the render path turn it
back on for their own scope while replacing httpx.post with a stub. That
way the code under test is the real code — including the httpx call site,
the base64 encoding, and the failure handling — with only the socket
replaced.
"""

import base64

import httpx
import pytest

from app.services import labels

# A one-pixel PNG is enough: what matters is that whatever bytes the
# renderer returns come back base64-encoded intact.
FAKE_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _StubResponse:
    def __init__(self, status_code=200, content=FAKE_PNG_BYTES):
        self.status_code = status_code
        self.content = content


def _create_source(client, *, barcode_value="ENSRC-00042", source_name="Grid electricity"):
    """Create org -> facility -> emission source, returning the source JSON."""
    organization = client.post(
        "/api/organizations",
        json={"name": "Labelled Corp", "industry_type": "manufacturing"},
    )
    assert organization.status_code == 201, organization.text

    facility = client.post(
        "/api/facilities",
        json={
            "organization_id": organization.json()["id"],
            "name": "Chennai Plant",
            "location": "Chennai, TN",
            "facility_type": "factory",
        },
    )
    assert facility.status_code == 201, facility.text

    body = {
        "facility_id": facility.json()["id"],
        "source_type": "ENERGY",
        "source_name": source_name,
        "unit_of_measurement": "kWh",
    }
    if barcode_value is not None:
        body["barcode_value"] = barcode_value

    source = client.post("/api/emission-sources", json=body)
    assert source.status_code == 201, source.text
    return source.json()


class TestGenerateLabel:
    def test_returns_valid_looking_zpl_containing_the_barcode(self, client):
        source = _create_source(client)

        response = client.get(f"/api/emission-sources/{source['id']}/label")
        assert response.status_code == 200, response.text

        body = response.json()
        zpl = body["zpl_code"]

        assert zpl.startswith("^XA")
        assert zpl.rstrip().endswith("^XZ")
        assert "ENSRC-00042" in zpl
        assert body["barcode_value"] == "ENSRC-00042"
        assert body["emission_source_id"] == source["id"]

    def test_zpl_carries_the_human_readable_fields(self, client):
        source = _create_source(client)

        zpl = client.get(f"/api/emission-sources/{source['id']}/label").json()["zpl_code"]

        assert "Grid electricity" in zpl, "source_name must be on the label"
        assert "Chennai Plant" in zpl, "facility name must be on the label"
        assert "ENERGY" in zpl, "source_type must be on the label"
        assert "kWh" in zpl, "unit_of_measurement must be on the label"

    def test_encodes_the_barcode_as_code_128(self, client):
        source = _create_source(client)

        zpl = client.get(f"/api/emission-sources/{source['id']}/label").json()["zpl_code"]

        # ^BC is Code 128; N = normal orientation, and the third parameter Y
        # prints the human-readable interpretation line under the bars.
        assert "^BCN,100,Y,N,N" in zpl
        assert "^BY" in zpl, "module width must be set before the barcode"

    def test_reports_the_geometry_the_zpl_was_built_for(self, client):
        source = _create_source(client)

        body = client.get(f"/api/emission-sources/{source['id']}/label").json()

        assert body["label_width_inches"] == 4.0
        assert body["label_height_inches"] == 2.0
        assert body["print_density_dpmm"] == 8
        # 4in x 25.4mm x 8dots/mm = 812 dots wide, 406 tall.
        assert "^PW812" in body["zpl_code"]
        assert "^LL406" in body["zpl_code"]

    def test_requires_authentication(self, client):
        source = _create_source(client)
        client.headers.pop("Authorization")

        response = client.get(f"/api/emission-sources/{source['id']}/label")
        assert response.status_code == 401


class TestLabelErrorCases:
    def test_missing_barcode_value_returns_422(self, client):
        source = _create_source(client, barcode_value=None)
        assert source["barcode_value"] is None

        response = client.get(f"/api/emission-sources/{source['id']}/label")
        assert response.status_code == 422

        error = response.json()["error"]
        assert error["code"] == "BARCODE_NOT_ASSIGNED"
        # The message has to tell the user what to do, not just what failed.
        assert "barcode" in error["message"].lower()
        assert "assign" in error["message"].lower()

    def test_nonexistent_emission_source_returns_404(self, client):
        response = client.get("/api/emission-sources/999999/label")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


class TestPreviewRendering:
    def test_includes_a_base64_png_when_the_renderer_responds(
        self, client, monkeypatch
    ):
        monkeypatch.setenv("LABEL_PREVIEW_ENABLED", "true")
        captured = {}

        def fake_post(url, **kwargs):
            captured["url"] = url
            captured["content"] = kwargs.get("content")
            captured["headers"] = kwargs.get("headers")
            return _StubResponse()

        monkeypatch.setattr(labels.httpx, "post", fake_post)
        source = _create_source(client)

        body = client.get(f"/api/emission-sources/{source['id']}/label").json()

        assert body["preview_png_base64"] is not None
        assert base64.b64decode(body["preview_png_base64"]) == FAKE_PNG_BYTES
        assert body["preview_note"] is None

        # The renderer must be asked for exactly the label this ZPL describes.
        assert "8dpmm" in captured["url"]
        assert "4x2" in captured["url"]
        assert captured["headers"]["Accept"] == "image/png"
        assert captured["content"] == body["zpl_code"].encode("utf-8")

    def test_unreachable_renderer_still_returns_the_zpl(self, client, monkeypatch):
        """The whole point of requirement 2: an optional cosmetic preview
        must never take the endpoint down with it."""
        monkeypatch.setenv("LABEL_PREVIEW_ENABLED", "true")

        def fake_post(url, **kwargs):
            raise httpx.ConnectError("labelary.com unreachable")

        monkeypatch.setattr(labels.httpx, "post", fake_post)
        source = _create_source(client)

        response = client.get(f"/api/emission-sources/{source['id']}/label")

        assert response.status_code == 200, "a dead renderer must not fail the request"
        body = response.json()
        assert body["preview_png_base64"] is None
        assert "unreachable" in body["preview_note"].lower()
        assert body["zpl_code"].startswith("^XA")
        assert "ENSRC-00042" in body["zpl_code"]

    def test_renderer_error_status_is_treated_as_unavailable(
        self, client, monkeypatch
    ):
        monkeypatch.setenv("LABEL_PREVIEW_ENABLED", "true")
        monkeypatch.setattr(
            labels.httpx, "post", lambda url, **kwargs: _StubResponse(status_code=503)
        )
        source = _create_source(client)

        body = client.get(f"/api/emission-sources/{source['id']}/label").json()

        assert body["preview_png_base64"] is None
        assert body["preview_note"] is not None
        assert body["zpl_code"].startswith("^XA")

    def test_preview_false_skips_the_outbound_call_entirely(
        self, client, monkeypatch
    ):
        monkeypatch.setenv("LABEL_PREVIEW_ENABLED", "true")

        def fail_if_called(url, **kwargs):
            raise AssertionError("preview=false must not call the renderer")

        monkeypatch.setattr(labels.httpx, "post", fail_if_called)
        source = _create_source(client)

        body = client.get(
            f"/api/emission-sources/{source['id']}/label?preview=false"
        ).json()

        assert body["preview_png_base64"] is None
        assert "disabled" in body["preview_note"].lower()
        assert body["zpl_code"].startswith("^XA")


class TestZplEscaping:
    """^ and ~ are ZPL control characters. Left raw in a field they would
    terminate it and turn label text into commands, so they are rewritten as
    ^FH_ hex escapes."""

    def test_control_characters_in_a_name_do_not_leak_into_commands(self, client):
        source = _create_source(client, source_name="Boiler ^ Unit ~ 3")

        zpl = client.get(f"/api/emission-sources/{source['id']}/label").json()["zpl_code"]

        field_line = next(line for line in zpl.splitlines() if "Boiler" in line)
        assert "_5E" in field_line, "^ must be hex-escaped"
        assert "_7E" in field_line, "~ must be hex-escaped"
        assert "^FH_" in field_line, "the field must declare the hex indicator"
        # Exactly the field's own commands remain: ^FO, ^A0N, ^FH, ^FD, ^FS.
        assert field_line.count("^") == 5

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("plain", "plain"),
            ("under_score", "under_5Fscore"),
            ("caret^here", "caret_5Ehere"),
            ("tilde~here", "tilde_7Ehere"),
            # The underscore must be escaped first, or escaping ^ would
            # produce a _5E that the next pass mangles into _5F5E.
            ("_^", "_5F_5E"),
        ],
    )
    def test_escape_rules(self, raw, expected):
        assert labels._escape_zpl(raw) == expected

    def test_long_source_name_is_trimmed_to_fit_the_label(self, client):
        long_name = "Combined heat and power turbine number seventeen, east wing"
        source = _create_source(client, source_name=long_name)

        zpl = client.get(f"/api/emission-sources/{source['id']}/label").json()["zpl_code"]

        title_line = next(line for line in zpl.splitlines() if "^A0N,40,40" in line)
        assert "..." in title_line, "an overlong name must be visibly trimmed"
        assert long_name not in title_line
