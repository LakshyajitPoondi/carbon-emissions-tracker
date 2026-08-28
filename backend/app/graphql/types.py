"""Strawberry GraphQL types mirroring the existing SQLAlchemy models.

These are read-only projections built from ORM rows by the resolvers in
schema.py — not the ORM models themselves. Field names are declared
snake_case (matching the models and the REST schemas); Strawberry's default
auto_camel_case exposes them to GraphQL clients as camelCase
(emissions_summary -> emissionsSummary), matching typical GraphQL
convention without needing every field renamed by hand.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import strawberry

from app.models.emission_source import SourceTypeEnum
from app.models.facility import Facility as FacilityModel
from app.models.organization import Organization as OrganizationModel

# Reuses the same enum the REST schemas and the SQLAlchemy model use —
# ENERGY / FUEL / RESOURCE — as a proper GraphQL enum rather than a bare
# string, so a GraphQL client gets the same validation/introspection REST
# clients get from the contract.
SourceType = strawberry.enum(SourceTypeEnum, name="SourceType")


@strawberry.type
class EmissionsSummaryType:
    """Mirrors docs/api-contract.md's GET /facilities/{id}/emissions-summary
    response shape — same fields, same Decimal-as-string serialization
    (Strawberry maps python Decimal to a GraphQL scalar that serializes as
    a string, matching how the REST response already renders these
    numbers)."""

    facility_id: int
    period_start: date
    period_end: date
    total_emissions_kg_co2e: Decimal
    by_source_type: strawberry.scalars.JSON


@strawberry.type
class EmissionSourceType:
    """Mirrors docs/api-contract.md's Emission Sources response shape."""

    id: int
    facility_id: int
    source_type: SourceType
    source_name: str
    unit_of_measurement: str
    barcode_value: Optional[str]
    created_at: datetime
    updated_at: datetime


@strawberry.type
class FacilityType:
    id: int
    organization_id: int
    name: str
    location: str
    facility_type: str
    created_at: datetime
    updated_at: datetime

    @strawberry.field(
        description="Emissions summary for this facility over [start_date, end_date], "
        "computed the same way as GET /facilities/{id}/emissions-summary."
    )
    async def emissions_summary(
        self, info: strawberry.Info, start_date: date, end_date: date
    ) -> EmissionsSummaryType:
        loader = info.context["emissions_loader"]
        return await loader.load((self.id, start_date, end_date))

    @strawberry.field(description="Emission sources belonging to this facility.")
    async def emission_sources(self, info: strawberry.Info) -> list[EmissionSourceType]:
        loader = info.context["emission_sources_loader"]
        return await loader.load(self.id)


@strawberry.type
class OrganizationType:
    id: int
    name: str
    industry_type: str
    created_at: datetime

    @strawberry.field(description="Facilities belonging to this organization.")
    def facilities(self, info: strawberry.Info) -> list[FacilityType]:
        db = info.context["db"]
        rows = db.query(FacilityModel).filter(FacilityModel.organization_id == self.id).all()
        return [facility_to_graphql(f) for f in rows]


def facility_to_graphql(facility: FacilityModel) -> FacilityType:
    return FacilityType(
        id=facility.id,
        organization_id=facility.organization_id,
        name=facility.name,
        location=facility.location,
        facility_type=facility.facility_type,
        created_at=facility.created_at,
        updated_at=facility.updated_at,
    )


def organization_to_graphql(organization: OrganizationModel) -> OrganizationType:
    return OrganizationType(
        id=organization.id,
        name=organization.name,
        industry_type=organization.industry_type,
        created_at=organization.created_at,
    )
