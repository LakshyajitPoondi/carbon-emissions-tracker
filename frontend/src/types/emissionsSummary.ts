/** Mirrors docs/api-contract.md — Emissions Summary (dashboard) section. */

import type { SourceType } from "./emissionSource";

export interface EmissionsPeriod {
  start: string;
  end: string;
}

export interface EmissionsSummary {
  facility_id: number;
  period: EmissionsPeriod;
  /** Decimal string, e.g. "12045.30". */
  total_emissions_kg_co2e: string;
  by_source_type: Record<SourceType, string>;
}
