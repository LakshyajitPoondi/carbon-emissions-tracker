/** Mirrors docs/api-contract.md — Reports section. */

export type ReportStatus = "draft" | "final";

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

/** GET /reports list item — no nested facilities breakdown. */
export interface ReportSummary {
  id: number;
  organization_id: number;
  report_period_start: string;
  report_period_end: string;
  generated_at: string;
  status: ReportStatus;
  total_emissions_kg_co2e: string;
}

/** POST /reports/generate and GET /reports/{id} response. */
export interface Report extends ReportSummary {
  facilities: FacilityBreakdown[];
}
