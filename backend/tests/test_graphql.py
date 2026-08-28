"""Tests for the read-only GraphQL layer at /graphql.

Covers: the organization(id) query returns nested data matching what the
equivalent REST calls return, auth is enforced on POST the same as every
REST endpoint while GET serves the GraphiQL console unauthenticated (and
can never execute a query), a nonexistent organization surfaces a
GraphQL-style error instead of crashing, and the emissionsSummary field
batches into one query per distinct period instead of one query per
facility (the N+1 concern from docs/api-contract.md's GraphQL section).
"""

import pytest
from sqlalchemy import event

ORGANIZATION_QUERY = """
query Q($orgId: Int!, $start: Date!, $end: Date!) {
  organization(id: $orgId) {
    id
    name
    industryType
    facilities {
      id
      organizationId
      name
      location
      facilityType
      emissionsSummary(startDate: $start, endDate: $end) {
        facilityId
        periodStart
        periodEnd
        totalEmissionsKgCo2e
        bySourceType
      }
    }
  }
}
"""


def _make_org_and_facility(client, name="GraphQL Org", facility_name="GraphQL Plant"):
    org_resp = client.post(
        "/api/organizations",
        json={"name": name, "industry_type": "manufacturing"},
    )
    org_id = org_resp.json()["id"]
    fac_resp = client.post(
        "/api/facilities",
        json={
            "organization_id": org_id,
            "name": facility_name,
            "location": "Chennai, TN",
            "facility_type": "factory",
        },
    )
    return org_id, fac_resp.json()["id"]


def _make_source(client, facility_id, source_type):
    resp = client.post(
        "/api/emission-sources",
        json={
            "facility_id": facility_id,
            "source_type": source_type,
            "source_name": f"{source_type} source",
            "unit_of_measurement": "unit",
        },
    )
    return resp.json()["id"]


class TestOrganizationQuery:
    def test_matches_rest_response_shape(self, client):
        org_id, facility_id = _make_org_and_facility(client)
        energy_source = _make_source(client, facility_id, "ENERGY")
        client.post(
            "/api/consumption-records",
            json={
                "emission_source_id": energy_source,
                "facility_id": facility_id,
                "quantity_consumed": "1000",
                "unit": "kWh",
                "recorded_at": "2026-08-05T00:00:00Z",
            },
        )

        rest_summary = client.get(
            f"/api/facilities/{facility_id}/emissions-summary",
            params={"start_date": "2026-08-01", "end_date": "2026-08-26"},
        ).json()
        rest_facility = client.get(f"/api/facilities?organization_id={org_id}").json()[0]
        rest_org = client.get(f"/api/organizations/{org_id}").json()

        resp = client.post(
            "/graphql",
            json={
                "query": ORGANIZATION_QUERY,
                "variables": {"orgId": org_id, "start": "2026-08-01", "end": "2026-08-26"},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("errors") is None, body.get("errors")

        gql_org = body["data"]["organization"]
        assert gql_org["id"] == rest_org["id"]
        assert gql_org["name"] == rest_org["name"]
        assert gql_org["industryType"] == rest_org["industry_type"]
        assert len(gql_org["facilities"]) == 1

        gql_facility = gql_org["facilities"][0]
        assert gql_facility["id"] == rest_facility["id"]
        assert gql_facility["name"] == rest_facility["name"]
        assert gql_facility["location"] == rest_facility["location"]
        assert gql_facility["facilityType"] == rest_facility["facility_type"]

        gql_summary = gql_facility["emissionsSummary"]
        assert gql_summary["facilityId"] == rest_summary["facility_id"]
        assert gql_summary["periodStart"] == rest_summary["period"]["start"]
        assert gql_summary["periodEnd"] == rest_summary["period"]["end"]
        assert gql_summary["totalEmissionsKgCo2e"] == rest_summary["total_emissions_kg_co2e"]
        assert gql_summary["bySourceType"] == rest_summary["by_source_type"]
        # Sanity on the actual number, not just cross-API agreement.
        assert gql_summary["totalEmissionsKgCo2e"] == "708.20"

    def test_multiple_facilities_each_get_correct_totals(self, client):
        org_id, facility_a = _make_org_and_facility(client, "Multi Org", "Plant A")
        fac_b_resp = client.post(
            "/api/facilities",
            json={
                "organization_id": org_id,
                "name": "Plant B",
                "location": "Mumbai, MH",
                "facility_type": "factory",
            },
        )
        facility_b = fac_b_resp.json()["id"]

        source_a = _make_source(client, facility_a, "ENERGY")
        source_b = _make_source(client, facility_b, "FUEL")
        client.post(
            "/api/consumption-records",
            json={
                "emission_source_id": source_a,
                "facility_id": facility_a,
                "quantity_consumed": "1000",
                "unit": "kWh",
                "recorded_at": "2026-08-05T00:00:00Z",
            },
        )
        client.post(
            "/api/consumption-records",
            json={
                "emission_source_id": source_b,
                "facility_id": facility_b,
                "quantity_consumed": "100",
                "unit": "litre",
                "recorded_at": "2026-08-10T00:00:00Z",
            },
        )

        resp = client.post(
            "/graphql",
            json={
                "query": ORGANIZATION_QUERY,
                "variables": {"orgId": org_id, "start": "2026-08-01", "end": "2026-08-26"},
            },
        )
        body = resp.json()
        assert body.get("errors") is None, body.get("errors")
        facilities = {f["id"]: f["emissionsSummary"] for f in body["data"]["organization"]["facilities"]}

        assert facilities[facility_a]["totalEmissionsKgCo2e"] == "708.20"
        assert facilities[facility_a]["bySourceType"]["FUEL"] == "0.00"
        assert facilities[facility_b]["totalEmissionsKgCo2e"] == "268.30"
        assert facilities[facility_b]["bySourceType"]["ENERGY"] == "0.00"

    def test_nonexistent_organization_returns_graphql_error(self, client):
        resp = client.post(
            "/graphql",
            json={"query": "{ organization(id: 999999) { id name } }"},
        )
        # A field-level GraphQL error is still a 200 transport response —
        # the error lives in the body's "errors" array, not the HTTP status.
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == {"organization": None}
        assert len(body["errors"]) == 1
        assert body["errors"][0]["extensions"]["code"] == "NOT_FOUND"
        assert "999999" in body["errors"][0]["message"]


class TestEmissionSourcesField:
    def test_matches_rest_list_endpoint(self, client):
        org_id, facility_id = _make_org_and_facility(client)
        _make_source(client, facility_id, "ENERGY")
        _make_source(client, facility_id, "FUEL")

        rest_sources = client.get(f"/api/emission-sources?facility_id={facility_id}").json()

        resp = client.post(
            "/graphql",
            json={
                "query": """
                query Q($orgId: Int!) {
                  organization(id: $orgId) {
                    facilities {
                      id
                      emissionSources {
                        id
                        facilityId
                        sourceType
                        sourceName
                        unitOfMeasurement
                        barcodeValue
                      }
                    }
                  }
                }
                """,
                "variables": {"orgId": org_id},
            },
        )
        body = resp.json()
        assert body.get("errors") is None, body.get("errors")
        gql_sources = body["data"]["organization"]["facilities"][0]["emissionSources"]

        assert {s["id"] for s in gql_sources} == {s["id"] for s in rest_sources}
        by_id = {s["id"]: s for s in rest_sources}
        for gql_source in gql_sources:
            rest_source = by_id[gql_source["id"]]
            assert gql_source["sourceType"] == rest_source["source_type"]
            assert gql_source["sourceName"] == rest_source["source_name"]
            assert gql_source["unitOfMeasurement"] == rest_source["unit_of_measurement"]
            assert gql_source["barcodeValue"] == rest_source["barcode_value"]

    def test_batches_into_one_query_not_one_per_facility(self, client, db_session):
        org_resp = client.post(
            "/api/organizations",
            json={"name": "Sources N+1 Org", "industry_type": "manufacturing"},
        )
        org_id = org_resp.json()["id"]
        for i in range(3):
            fac_resp = client.post(
                "/api/facilities",
                json={
                    "organization_id": org_id,
                    "name": f"Sources Facility {i}",
                    "location": "Somewhere",
                    "facility_type": "factory",
                },
            )
            _make_source(client, fac_resp.json()["id"], "ENERGY")

        connection = db_session.get_bind()
        statements: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(connection, "before_cursor_execute", _capture)
        try:
            resp = client.post(
                "/graphql",
                json={
                    "query": """
                    query Q($orgId: Int!) {
                      organization(id: $orgId) {
                        facilities { id emissionSources { id sourceName } }
                      }
                    }
                    """,
                    "variables": {"orgId": org_id},
                },
            )
        finally:
            event.remove(connection, "before_cursor_execute", _capture)

        body = resp.json()
        assert body.get("errors") is None, body.get("errors")
        for facility in body["data"]["organization"]["facilities"]:
            assert len(facility["emissionSources"]) == 1

        source_queries = [s for s in statements if "emission_sources" in s.lower()]
        assert len(source_queries) == 1, (
            f"expected exactly 1 batched emission_sources query, got {len(source_queries)}:\n"
            + "\n---\n".join(source_queries)
        )


class TestGraphQLAuth:
    def test_request_without_token_returns_401(self, client):
        del client.headers["Authorization"]
        resp = client.post("/graphql", json={"query": "{ organization(id: 1) { id } }"})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"

    def test_request_with_invalid_token_returns_401(self, client):
        client.headers["Authorization"] = "Bearer not-a-real-token"
        resp = client.post("/graphql", json={"query": "{ organization(id: 1) { id } }"})
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"


class TestGraphiQLConsoleAccess:
    """GET serves the console; POST is what needs a token.

    The pairing matters: a browser navigating to /graphql cannot send an
    Authorization header, so gating GET made the console unreachable. GET is
    exempt from auth *because* the router is built with
    allow_queries_via_get=False — without that, exempting GET would hand out
    unauthenticated read access to the whole schema via a query string. The
    last two tests here are what keep those two settings honest.
    """

    def test_graphiql_page_loads_without_a_token(self, client):
        del client.headers["Authorization"]
        resp = client.get("/graphql")

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/html")
        assert "graphiql" in resp.text.lower()

    def test_post_still_requires_a_token(self, client):
        """The console being public must not make the data public."""
        del client.headers["Authorization"]
        resp = client.post("/graphql", json={"query": "{ __typename }"})

        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"

    @pytest.mark.parametrize("accept", ["text/html", "application/json"])
    def test_unauthenticated_get_with_a_query_string_does_not_return_data(
        self, client, accept
    ):
        """The exemption's blast radius, pinned. An unauthenticated GET
        carrying a query must never execute it, whatever it asks for back."""
        del client.headers["Authorization"]
        resp = client.get("/graphql?query={__typename}", headers={"Accept": accept})

        assert resp.status_code == 400
        assert "not allowed" in resp.text.lower()
        # Nothing that could be a GraphQL result came back.
        assert "__typename" not in resp.text
        assert "Query" not in resp.text
        with pytest.raises(ValueError):
            resp.json()

    def test_authenticated_get_with_a_query_string_is_refused_too(self, client):
        """Not merely an auth check: GET cannot execute queries at all, so a
        valid token doesn't unlock the GET path either. That is what stops
        query execution from ever depending on the auth exemption."""
        resp = client.get("/graphql?query={__typename}")

        assert resp.status_code == 400
        assert "not allowed" in resp.text.lower()

    def test_a_real_query_still_works_over_post(self, client):
        """The console is only useful if the flow it documents works: load
        the page unauthenticated, then POST with the token pasted into
        GraphiQL's Headers pane."""
        org = client.post(
            "/api/organizations",
            json={"name": "Console Corp", "industry_type": "manufacturing"},
        ).json()

        resp = client.post(
            "/graphql",
            json={
                "query": "query Q($id: Int!) { organization(id: $id) { name industryType } }",
                "variables": {"id": org["id"]},
            },
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["organization"] == {
            "name": "Console Corp",
            "industryType": "manufacturing",
        }


class TestEmissionsSummaryNPlusOne:
    def test_batches_into_one_query_per_period_not_one_per_facility(self, client, db_session):
        """3 facilities under one organization, same period, in one query —
        should fire exactly one grouped SQL query for the emissions
        aggregation (via organization_emissions_by_source_type), not 3."""
        org_resp = client.post(
            "/api/organizations",
            json={"name": "N+1 Check Org", "industry_type": "manufacturing"},
        )
        org_id = org_resp.json()["id"]
        facility_ids = []
        for i in range(3):
            fac_resp = client.post(
                "/api/facilities",
                json={
                    "organization_id": org_id,
                    "name": f"Facility {i}",
                    "location": "Somewhere",
                    "facility_type": "factory",
                },
            )
            facility_id = fac_resp.json()["id"]
            facility_ids.append(facility_id)
            source_id = _make_source(client, facility_id, "ENERGY")
            client.post(
                "/api/consumption-records",
                json={
                    "emission_source_id": source_id,
                    "facility_id": facility_id,
                    "quantity_consumed": "10",
                    "unit": "kWh",
                    "recorded_at": "2026-08-05T00:00:00Z",
                },
            )

        query = """
        query Q($orgId: Int!, $start: Date!, $end: Date!) {
          organization(id: $orgId) {
            facilities {
              id
              emissionsSummary(startDate: $start, endDate: $end) {
                totalEmissionsKgCo2e
              }
            }
          }
        }
        """

        connection = db_session.get_bind()
        statements: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(connection, "before_cursor_execute", _capture)
        try:
            resp = client.post(
                "/graphql",
                json={
                    "query": query,
                    "variables": {"orgId": org_id, "start": "2026-08-01", "end": "2026-08-26"},
                },
            )
        finally:
            event.remove(connection, "before_cursor_execute", _capture)

        body = resp.json()
        assert body.get("errors") is None, body.get("errors")
        for facility in body["data"]["organization"]["facilities"]:
            assert facility["emissionsSummary"]["totalEmissionsKgCo2e"] == "7.08"

        emissions_queries = [
            s for s in statements if "consumption_records" in s.lower() and "emission_calculations" in s.lower()
        ]
        assert len(emissions_queries) == 1, (
            f"expected exactly 1 batched emissions query for {len(facility_ids)} facilities "
            f"sharing one period, got {len(emissions_queries)}:\n" + "\n---\n".join(emissions_queries)
        )
