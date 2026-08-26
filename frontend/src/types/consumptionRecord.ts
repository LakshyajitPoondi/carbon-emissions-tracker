/** Mirrors docs/api-contract.md — Consumption Records section. */

export interface EmissionCalculation {
  id: number;
  emission_factor_id: number;
  /** Decimal string, e.g. "885.679730". */
  calculated_emissions_kg_co2e: string;
  calculation_date: string;
}

export interface ConsumptionRecord {
  id: number;
  emission_source_id: number;
  facility_id: number;
  /** Decimal string, e.g. "1250.500000". */
  quantity_consumed: string;
  unit: string;
  recorded_at: string;
  created_at: string;
  calculation: EmissionCalculation | null;
}

export interface ConsumptionRecordCreateRequest {
  emission_source_id: number;
  facility_id: number;
  quantity_consumed: string;
  unit: string;
  recorded_at: string;
}
