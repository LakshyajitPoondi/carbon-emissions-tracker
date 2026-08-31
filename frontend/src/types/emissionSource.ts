/** Mirrors docs/api-contract.md — Emission Sources section. */

export const SOURCE_TYPES = ["ENERGY", "FUEL", "RESOURCE"] as const;

export type SourceType = (typeof SOURCE_TYPES)[number];

export interface EmissionSource {
  id: number;
  facility_id: number;
  source_type: SourceType;
  source_name: string;
  unit_of_measurement: string;
  barcode_value: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmissionSourceCreateRequest {
  facility_id: number;
  source_type: SourceType;
  source_name: string;
  unit_of_measurement: string;
  barcode_value?: string | null;
}

export interface EmissionSourceUpdateRequest {
  source_type?: SourceType;
  source_name?: string;
  unit_of_measurement?: string;
  barcode_value?: string | null;
}
