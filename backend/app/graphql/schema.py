"""Root GraphQL schema + FastAPI router.

Read-only by design: one Query type, no Mutation type at all. REST stays
the source of truth for every create/update — see docs/api-contract.md's
GraphQL section.
"""

from typing import Optional

import strawberry
from fastapi import Depends, HTTPException
from graphql import GraphQLError
from sqlalchemy.orm import Session
from strawberry.fastapi import GraphQLRouter

from app.auth import get_current_user_for_graphql
from app.authorization import OrganizationAction, require_organization
from app.database import get_db
from app.graphql.loaders import make_emission_sources_loader, make_emissions_summary_loader
from app.graphql.types import OrganizationType, organization_to_graphql
from app.models.user import User


@strawberry.type
class Query:
    @strawberry.field(
        description="An organization with its facilities and, per facility, an emissions "
        "summary for a given period. Returns a GraphQL error (not an HTTP error) if the "
        "organization doesn't exist."
    )
    def organization(self, info: strawberry.Info, id: int) -> Optional[OrganizationType]:
        db: Session = info.context["db"]
        user = info.context["user"]
        # The same membership check the REST layer applies, so GraphQL is
        # not a second, unscoped door to the same rows. Nested fields
        # (facilities, emissionsSummary, emissionSources) are reachable only
        # through this resolver, so authorizing the root authorizes the
        # subtree — see test_graphql.py's root-fields guard, which fails if
        # a new unscoped root field is ever added.
        try:
            org = require_organization(
                db, user, id, OrganizationAction.VIEW
            )
        except HTTPException:
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


async def get_graphql_context(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_for_graphql),
) -> dict:
    """Per-request context: the same DB session REST endpoints use (via the
    same get_db dependency, so session lifecycle/rollback behavior is
    identical), plus a fresh DataLoader instance so batching never leaks
    cached results across requests, plus the authenticated user that
    resolvers scope their queries by.

    The user is resolved with get_current_user_for_graphql, the same lenient
    dependency the router uses, and is Optional for one specific reason:
    Strawberry builds a context for the GET that serves the GraphiQL console
    HTML too, not just for query execution. Requiring a token here would
    therefore 401 the console page and undo the GraphiQL fix — which is
    exactly what happened the first time this was written.

    It is never None where it matters. Queries are always POST (the router
    is built with allow_queries_via_get=False), and POST is gated by the
    strict path of that same dependency, so any resolver that reads
    context["user"] has a real user."""
    return {
        "db": db,
        "user": user,
        "emissions_loader": make_emissions_summary_loader(db),
        "emission_sources_loader": make_emission_sources_loader(db),
    }


# allow_queries_via_get=False is load-bearing, not tidiness. Strawberry
# defaults it to True, which lets GET /graphql?query={...} execute a real
# query. Auth for this router is gated on POST only (see
# app.auth.get_current_user_for_graphql) so that a browser can load the
# GraphiQL page without an Authorization header it has no way to send —
# and if GET could also execute queries, that exemption would hand out
# unauthenticated read access to the whole schema. With this off, GET can
# do exactly one thing: serve the static GraphiQL HTML shell.
graphql_router = GraphQLRouter(
    schema,
    context_getter=get_graphql_context,
    allow_queries_via_get=False,
)
