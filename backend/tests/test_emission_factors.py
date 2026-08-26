"""Tests for GET /api/emission-factors — seeded reference data, read-only."""


class TestListEmissionFactors:
    def test_no_filter_returns_all_seeded_factors(self, client):
        resp = client.get("/api/emission-factors")
        assert resp.status_code == 200
        data = resp.json()
        # app/seed.py seeds exactly one factor per source_type for region IN
        assert len(data) >= 3
        source_types = {row["source_type"] for row in data}
        assert {"ENERGY", "FUEL", "RESOURCE"}.issubset(source_types)

    def test_filter_by_source_type_and_region(self, client):
        resp = client.get("/api/emission-factors", params={"source_type": "ENERGY", "region": "IN"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        row = data[0]
        assert row["source_type"] == "ENERGY"
        assert row["region"] == "IN"
        assert row["factor_value"] == "0.708200"
        assert row["unit"] == "kg_co2e_per_kwh"
        assert row["valid_to"] is None

    def test_filter_with_no_match_returns_empty_list(self, client):
        resp = client.get("/api/emission-factors", params={"source_type": "ENERGY", "region": "US"})
        assert resp.status_code == 200
        assert resp.json() == []
