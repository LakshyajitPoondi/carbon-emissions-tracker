"""Root GraphQL schema + FastAPI router.

Read-only by design: one Query type, no Mutation type at all. REST stays
the source of truth for every create/update — see docs/api-contract.md's
GraphQL section.
"""

from typing import Optional

import strawberry
from fastapi import Depends
from graphql import GraphQLError
from sqlalchemy.orm import Session
from strawberry.fastapi import GraphQLRouter

from app.database import get_db
from app.graphql.loaders import make_emission_sources_loader, make_emissions_summary_loader
from app.graphql.types import OrganizationType, organization_to_graphql
from app.models.organization import Organization


@strawberry.type
class Query:
    @strawberry.field(
        description="An organization with its facilities and, per facility, an emissions "
        "summary for a given period. Returns a GraphQL error (not an HTTP error) if the "
        "organization doesn't exist."
    )
    def organization(self, info: strawberry.Info, id: int) -> Optional[OrganizationType]:
        db: Session = info.context["db"]
        org = db.get(Organization, id)
        if org is None:
            # Raising here (rather than returning None) is what makes this
            # show up in the response's "errors" array with a message and
            # an extensions.code, instead of a bare, unexplained null —
            # the GraphQL-native equivalent of REST's 404 + NOT_FOUND.
            raise GraphQLError(
                f"Organization {id} does not exist",
                extensions={"code": "NOT_FOUND"},
            )
        return organization_to_graphql(org)


schema = strawberry.Schema(query=Query)


async def get_graphql_context(db: Session = Depends(get_db)) -> dict:
    """Per-request context: the same DB session REST endpoints use (via the
    same get_db dependency, so session lifecycle/rollback behavior is
    identical), plus a fresh DataLoader instance so batching never leaks
    cached results across requests."""
    return {
        "db": db,
        "emissions_loader": make_emissions_summary_loader(db),
        "emission_sources_loader": make_emission_sources_loader(db),
    }


graphql_router = GraphQLRouter(schema, context_getter=get_graphql_context)
