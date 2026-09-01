"""Product Library CRUD, barcode generation, scoping, and role tests."""

import io

from PIL import Image
from pyzbar.pyzbar import decode

from app.models.organization_member import ROLE_ADMIN, ROLE_EMPLOYEE
from app.services.barcodes import is_valid_ean13


def _organization(client, name="Product Org"):
    response = client.post(
        "/api/organizations",
        json={"name": name, "industry_type": "manufacturing"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _product_body(organization_id: int, **overrides):
    body = {
        "organization_id": organization_id,
        "name": "Recycled aluminium bottle",
        "barcode": "8901234567890",
        "composition": "70% recycled aluminium, 30% primary aluminium",
        "emissions_value": "1.250000",
        "emissions_unit": "kg CO2e/item",
        "emissions_description": (
            "Cradle-to-gate embodied emissions per finished bottle"
        ),
        "source_reference": "Supplier EPD, 2026",
    }
    body.update(overrides)
    return body


def _create_product(client, organization_id: int, **overrides):
    response = client.post(
        "/api/products", json=_product_body(organization_id, **overrides)
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestProductCrud:
    def test_create_and_get_round_trip_all_fields(self, client):
        organization = _organization(client)
        created = _create_product(client, organization["id"])

        assert created["organization_id"] == organization["id"]
        assert created["name"] == "Recycled aluminium bottle"
        assert created["barcode"] == "8901234567890"
        assert created["composition"].startswith("70% recycled")
        assert created["emissions_value"] == "1.250000"
        assert created["emissions_unit"] == "kg CO2e/item"
        assert "Cradle-to-gate" in created["emissions_description"]
        assert created["source_reference"] == "Supplier EPD, 2026"
        assert created["created_at"]
        assert created["updated_at"]

        retrieved = client.get(f"/api/products/{created['id']}")
        assert retrieved.status_code == 200
        assert retrieved.json() == created

    def test_list_is_name_then_id_ordered(self, client):
        organization = _organization(client)
        zulu = _create_product(
            client, organization["id"], name="Zulu", barcode="BAR-Z"
        )
        alpha = _create_product(
            client, organization["id"], name="Alpha", barcode="BAR-A"
        )

        response = client.get(
            "/api/products", params={"organization_id": organization["id"]}
        )
        assert response.status_code == 200
        assert [product["id"] for product in response.json()] == [
            alpha["id"],
            zulu["id"],
        ]

    def test_patch_updates_fields_and_can_clear_barcode(self, client):
        organization = _organization(client)
        product = _create_product(client, organization["id"])

        updated = client.patch(
            f"/api/products/{product['id']}",
            json={
                "name": "Updated bottle",
                "barcode": None,
                "emissions_value": "1.100000",
                "source_reference": "Updated supplier EPD",
            },
        )
        assert updated.status_code == 200, updated.text
        body = updated.json()
        assert body["name"] == "Updated bottle"
        assert body["barcode"] is None
        assert body["emissions_value"] == "1.100000"
        assert body["source_reference"] == "Updated supplier EPD"
        assert body["composition"] == product["composition"]

    def test_delete_removes_product(self, client):
        organization = _organization(client)
        product = _create_product(client, organization["id"])

        deleted = client.delete(f"/api/products/{product['id']}")
        assert deleted.status_code == 204
        assert deleted.content == b""
        assert client.get(f"/api/products/{product['id']}").status_code == 404

    def test_missing_barcode_is_generated_with_persisted_png(self, client):
        organization = _organization(client)
        first = _create_product(
            client, organization["id"], name="Generated one", barcode=None
        )
        second = _create_product(
            client, organization["id"], name="Generated two", barcode="   "
        )

        assert first["barcode"] == "2000000000015"
        assert second["barcode"] == "2000000000022"
        assert is_valid_ean13(first["barcode"])
        assert is_valid_ean13(second["barcode"])

        image = client.get(f"/api/products/{first['id']}/barcode-image")
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"
        decoded = decode(Image.open(io.BytesIO(image.content)))
        assert [(item.type, item.data.decode()) for item in decoded] == [
            ("EAN13", first["barcode"])
        ]

    def test_valid_supplied_ean_gets_an_image_and_non_ean_does_not(self, client):
        organization = _organization(client)
        ean = _create_product(
            client, organization["id"], name="Supplied EAN", barcode="2000000001234"
        )
        arbitrary = _create_product(
            client, organization["id"], name="Arbitrary code", barcode="SKU-123"
        )

        assert client.get(f"/api/products/{ean['id']}/barcode-image").status_code == 200
        missing = client.get(f"/api/products/{arbitrary['id']}/barcode-image")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "NOT_FOUND"


class TestProductValidation:
    def test_null_and_blank_barcodes_trigger_generation(self, client):
        organization = _organization(client)
        first = _create_product(
            client, organization["id"], name="No barcode one", barcode=None
        )
        second = _create_product(
            client, organization["id"], name="No barcode two", barcode="   "
        )
        assert first["barcode"] is not None
        assert second["barcode"] is not None
        assert first["barcode"] != second["barcode"]
        assert is_valid_ean13(first["barcode"])
        assert is_valid_ean13(second["barcode"])

    def test_barcode_is_unique_within_an_organization(self, client):
        organization = _organization(client)
        _create_product(client, organization["id"], barcode="SAME-BARCODE")

        duplicate = client.post(
            "/api/products",
            json=_product_body(
                organization["id"], name="Duplicate", barcode="SAME-BARCODE"
            ),
        )
        assert duplicate.status_code == 422
        assert duplicate.json()["error"]["code"] == "BARCODE_ALREADY_ASSIGNED"

    def test_same_barcode_is_allowed_in_separate_organizations(self, client):
        first_organization = _organization(client, "First Product Org")
        second_organization = _organization(client, "Second Product Org")
        _create_product(client, first_organization["id"], barcode="SHARED-SKU")
        second = _create_product(
            client, second_organization["id"], barcode="SHARED-SKU"
        )
        assert second["barcode"] == "SHARED-SKU"

    def test_negative_emissions_and_empty_patch_are_rejected(self, client):
        organization = _organization(client)
        negative = client.post(
            "/api/products",
            json=_product_body(organization["id"], emissions_value="-0.1"),
        )
        assert negative.status_code == 422
        assert negative.json()["error"]["code"] == "VALIDATION_ERROR"

        product = _create_product(client, organization["id"], barcode="PATCH-ME")
        empty_patch = client.patch(f"/api/products/{product['id']}", json={})
        assert empty_patch.status_code == 422
        assert empty_patch.json()["error"]["code"] == "VALIDATION_ERROR"


class TestProductAuthorization:
    def test_nonmember_get_list_update_and_delete_are_masked(
        self, client, other_client
    ):
        organization = _organization(client)
        product = _create_product(client, organization["id"])

        assert other_client.get(f"/api/products/{product['id']}").status_code == 404
        assert (
            other_client.get(
                "/api/products", params={"organization_id": organization["id"]}
            ).status_code
            == 404
        )
        assert (
            other_client.patch(
                f"/api/products/{product['id']}", json={"name": "Intruder"}
            ).status_code
            == 404
        )
        assert other_client.delete(f"/api/products/{product['id']}").status_code == 404
        assert (
            other_client.get(f"/api/products/{product['id']}/barcode-image").status_code
            == 404
        )

    def test_employee_can_view_but_cannot_mutate(
        self, client, other_client, other_user, grant_membership
    ):
        organization = _organization(client)
        product = _create_product(client, organization["id"])
        grant_membership(other_user.id, organization["id"], ROLE_EMPLOYEE)

        assert other_client.get(f"/api/products/{product['id']}").status_code == 200
        assert (
            other_client.get(
                "/api/products", params={"organization_id": organization["id"]}
            ).status_code
            == 200
        )
        assert (
            other_client.get(f"/api/products/{product['id']}/barcode-image").status_code
            == 200
        )
        assert (
            other_client.post(
                "/api/products",
                json=_product_body(
                    organization["id"], name="Employee write", barcode="NOPE"
                ),
            ).status_code
            == 404
        )
        assert (
            other_client.patch(
                f"/api/products/{product['id']}", json={"name": "Nope"}
            ).status_code
            == 404
        )
        assert other_client.delete(f"/api/products/{product['id']}").status_code == 404

    def test_admin_can_create_update_and_delete(
        self, client, other_client, other_user, grant_membership
    ):
        organization = _organization(client)
        grant_membership(other_user.id, organization["id"], ROLE_ADMIN)

        created = other_client.post(
            "/api/products",
            json=_product_body(organization["id"], barcode="ADMIN-SKU"),
        )
        assert created.status_code == 201, created.text
        product_id = created.json()["id"]
        assert (
            other_client.patch(
                f"/api/products/{product_id}", json={"name": "Admin updated"}
            ).status_code
            == 200
        )
        assert other_client.delete(f"/api/products/{product_id}").status_code == 204
