"""GraphQL read-only query layer.

Mounted at /graphql (see app/main.py), protected by the same JWT auth as
every REST endpoint. REST remains the source of truth for all writes — this
package defines queries only, no mutations, and every resolver reads
through the same app/services functions REST already uses rather than
reimplementing aggregation logic a second time.
"""
