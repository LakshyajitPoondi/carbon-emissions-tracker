/** Mirrors docs/api-contract.md — Reports section.
 *
 * Generation is asynchronous (Celery + Redis): a report is created in
 * "pending" status, moves to "processing" while the worker aggregates, and
 * only "final" once its totals are computed and stored. "draft" is listed
 * in the contract as unused/predating this flow but kept here so the type
 * stays an exact mirror.
 */
export type ReportStatus = "draft" | "pending" | "processing" | "final";

export interface FacilityBreakdown {
  facility_id: number;
  facility_name: string;
  /** Decimal string, e.g. "12045.30". */
  total_emissions_kg_co2e: string;
}

export interface ReportGenerateRequest {
  organization_id: number;
  report_period_start: string;
  report_period_end: string;
}

/** GET /reports list item — no nested facilities breakdown.
 *
 * `total_emissions_kg_co2e` is `null` until `status` is "final" — a
 * report's totals are computed exactly once by the background worker and
 * stored, never recomputed on read, so there's nothing to show before
 * then.
 */
export interface ReportSummary {
  id: number;
  organization_id: number;
  report_period_start: string;
  report_period_end: string;
  generated_at: string;
  status: ReportStatus;
  total_emissions_kg_co2e: string | null;
}

/** POST /reports/generate and GET /reports/{id} response.
 *
 * `facilities` is `null` under the same condition as
 * `total_emissions_kg_co2e` above (non-"final" status).
 */
export interface Report extends ReportSummary {
  facilities: FacilityBreakdown[] | null;
}
