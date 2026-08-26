/** Mirrors docs/api-contract.md — Emission Factors section. Read-only; seeded server-side. */

import type { SourceType } from "./emissionSource";

export interface EmissionFactor {
  id: number;
  source_type: SourceType;
  region: string;
  /** Decimal string, e.g. "0.708200" — never parse and re-render as a float. */
  factor_value: string;
  unit: string;
  valid_from: string;
  valid_to: string | null;
  source_reference: string;
}
