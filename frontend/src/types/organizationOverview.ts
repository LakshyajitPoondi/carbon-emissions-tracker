/** Shapes returned by the GraphQL `organization(id:)` query.
 *
 * These mirror the schema as introspected from the live endpoint, not the
 * REST contract — GraphQL field names are camelCase and decimals arrive as
 * strings, the same convention REST uses for decimal fields.
 *
 * Note there is deliberately no organization-level total in the schema:
 * EmissionsSummaryType is per-facility only, so the org-wide figure is
 * summed on the client. See OrganizationOverviewPage.
 */

import type { SourceType } from "./emissionSource";

export interface GraphQLEmissionsSummary {
  facilityId: number;
  /** YYYY-MM-DD. */
  periodStart: string;
  periodEnd: string;
  /** Decimal string, e.g. "12045.30". */
  totalEmissionsKgCo2e: string;
  /** e.g. { "ENERGY": "8000.10", "FUEL": "3500.20", "RESOURCE": "545.00" } */
  bySourceType: Record<SourceType, string>;
}

export interface GraphQLOverviewFacility {
  id: number;
  name: string;
  location: string;
  emissionsSummary: GraphQLEmissionsSummary;
}

export interface OrganizationOverview {
  id: number;
  name: string;
  industryType: string;
  facilities: GraphQLOverviewFacility[];
}
