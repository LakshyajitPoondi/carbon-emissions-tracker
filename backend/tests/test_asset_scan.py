"""Tests for POST /api/facilities/{facility_id}/asset-scan.

Covers: successful decode+match, BARCODE_NOT_MATCHED (decoded but unmatched),
NO_BARCODE_DETECTED in both sub-cases (an object was in frame vs. nothing at
all), and that the YOLO model is loaded exactly once at startup, never
per-request.
"""

import io

import qrcode
from PIL import Image

from app.database import get_db
from app.main import app
from app.ml import get_yolo_model


def _qr_image_bytes(data: str) -> bytes:
    img = qrcode.make(data)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _blank_image_bytes() -> bytes:
    """No barcode anywhere in this — pyzbar will reliably decode nothing."""
    img = Image.new("RGB", (200, 200), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _create_org_facility(client):
    org = client.post(
        "/api/organizations", json={"name": "Scan Co", "industry_type": "manufacturing"}
    ).json()
    facility = client.post(
        "/api/facilities",
        json={
            "organization_id": org["id"],
            "name": "Scan Plant",
            "location": "Chennai, TN",
            "facility_type": "factory",
        },
    ).json()
    return org, facility


class _FakeBoxes:
    def __init__(self, confidences):
        self.conf = confidences


class _FakeResult:
    def __init__(self, confidences):
        self.boxes = _FakeBoxes(confidences)


class FakeYoloModel:
    """Stand-in for the loaded YOLO model, injected via dependency_overrides
    so the presence gate's found/not-found result is fully controllable —
    no real inference, no dependency on the actual weights file."""

    def __init__(self, confidences):
        self._confidences = confidences

    def predict(self, *args, **kwargs):
        return [_FakeResult(self._confidences)]


class TestAssetScanSuccess:
    def test_decode_and_match(self, client):
        _, facility = _create_org_facility(client)
        source = client.post(
            "/api/emission-sources",
            json={
                "facility_id": facility["id"],
                "source_type": "ENERGY",
                "source_name": "Grid electricity",
                "unit_of_measurement": "kWh",
                "barcode_value": "ENSRC-TEST-001",
            },
        ).json()

        resp = client.post(
            f"/api/facilities/{facility['id']}/asset-scan",
            files={"image": ("frame.png", _qr_image_bytes("ENSRC-TEST-001"), "image/png")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["decoded_value"] == "ENSRC-TEST-001"
        assert data["emission_source"]["id"] == source["id"]
        assert set(data["bounding_box"].keys()) == {"x", "y", "width", "height"}
        assert "confidence" not in data  # decode is pass/fail, not scored — see Decision B


class TestBarcodeNotMatched:
    def test_decoded_but_no_matching_source(self, client):
        _, facility = _create_org_facility(client)
        resp = client.post(
            f"/api/facilities/{facility['id']}/asset-scan",
            files={"image": ("frame.png", _qr_image_bytes("UNREGISTERED-BARCODE-XYZ"), "image/png")},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"]["code"] == "BARCODE_NOT_MATCHED"
        assert "UNREGISTERED-BARCODE-XYZ" in data["error"]["message"]

    def test_matched_source_in_different_facility_still_not_matched(self, client):
        # Same barcode value registered in facility A must not match a scan
        # against facility B — the uniqueness/lookup is facility-scoped.
        _, facility_a = _create_org_facility(client)
        _, facility_b = _create_org_facility(client)
        client.post(
            "/api/emission-sources",
            json={
                "facility_id": facility_a["id"],
                "source_type": "FUEL",
                "source_name": "Diesel generator",
                "unit_of_measurement": "litre",
                "barcode_value": "SHARED-CODE-001",
            },
        )
        resp = client.post(
            f"/api/facilities/{facility_b['id']}/asset-scan",
            files={"image": ("frame.png", _qr_image_bytes("SHARED-CODE-001"), "image/png")},
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "BARCODE_NOT_MATCHED"


class TestNoBarcodeDetected:
    def test_nothing_in_frame_at_all(self, client):
        app.dependency_overrides[get_yolo_model] = lambda: FakeYoloModel([])
        try:
            _, facility = _create_org_facility(client)
            resp = client.post(
                f"/api/facilities/{facility['id']}/asset-scan",
                files={"image": ("frame.png", _blank_image_bytes(), "image/png")},
            )
            assert resp.status_code == 422
            data = resp.json()
            assert data["error"]["code"] == "NO_BARCODE_DETECTED"
            assert "object was detected" not in data["error"]["message"]
        finally:
            app.dependency_overrides.pop(get_yolo_model, None)

    def test_object_detected_but_no_readable_barcode(self, client):
        app.dependency_overrides[get_yolo_model] = lambda: FakeYoloModel([0.83])
        try:
            _, facility = _create_org_facility(client)
            resp = client.post(
                f"/api/facilities/{facility['id']}/asset-scan",
                files={"image": ("frame.png", _blank_image_bytes(), "image/png")},
            )
            assert resp.status_code == 422
            data = resp.json()
            assert data["error"]["code"] == "NO_BARCODE_DETECTED"
            assert "object was detected" in data["error"]["message"]
        finally:
            app.dependency_overrides.pop(get_yolo_model, None)


class TestModelLoadedOnceAtStartup:
    def test_model_loaded_once_not_per_request(self, db_session, monkeypatch):
        """Directly verifies the requirement from docs/asset-scan-plan.md
        point 7: the model must load once at process startup (FastAPI
        lifespan), never lazily per-request. Patches the YOLO class itself
        (not just the dependency) and counts constructions across multiple
        real requests to this endpoint."""
        import app.ml as ml_module
        from fastapi.testclient import TestClient

        call_count = {"n": 0}

        class _CountingFakeYolo:
            def __init__(self, *args, **kwargs):
                call_count["n"] += 1

        monkeypatch.setattr(ml_module, "YOLO", _CountingFakeYolo)
        monkeypatch.delenv("SKIP_MODEL_LOAD", raising=False)

        def _override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = _override_get_db
        try:
            with TestClient(app) as c:
                register = c.post(
                    "/api/auth/register",
                    json={"email": "startup-test@example.com", "password": "startup-pass-123"},
                )
                assert register.status_code == 201
                token = c.post(
                    "/api/auth/token",
                    data={"username": "startup-test@example.com", "password": "startup-pass-123"},
                ).json()["access_token"]
                c.headers["Authorization"] = f"Bearer {token}"

                # The model must already be loaded by the time the app is up
                # and serving requests — before any scan request happens.
                assert call_count["n"] == 1

                org = c.post(
                    "/api/organizations", json={"name": "Startup Co", "industry_type": "manufacturing"}
                ).json()
                facility = c.post(
                    "/api/facilities",
                    json={
                        "organization_id": org["id"],
                        "name": "Startup Plant",
                        "location": "Chennai, TN",
                        "facility_type": "factory",
                    },
                ).json()

                image_bytes = _qr_image_bytes("STARTUP-TEST-001")
                for _ in range(3):
                    resp = c.post(
                        f"/api/facilities/{facility['id']}/asset-scan",
                        files={"image": ("frame.png", image_bytes, "image/png")},
                    )
                    assert resp.status_code == 422  # BARCODE_NOT_MATCHED — irrelevant here
                    assert call_count["n"] == 1  # never reloaded across repeated requests
        finally:
            app.dependency_overrides.pop(get_db, None)
