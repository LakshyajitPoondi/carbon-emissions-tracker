/** Mirrors docs/api-contract.md — Consumption Records section. */
import type { SourceType } from "./emissionSource";

export interface EmissionCalculation {
  id: number;
  emission_factor_id: number | null;
  /** Decimal string, e.g. "885.679730". */
  calculated_emissions_kg_co2e: string;
  calculation_date: string;
}

export interface ConsumptionRecord {
  id: number;
  emission_source_id: number | null;
  product_id: number | null;
  product_snapshot: ProductConsumptionSnapshot | null;
  facility_id: number;
  /** Decimal string, e.g. "1250.500000". */
  quantity_consumed: string;
  unit: string;
  recorded_at: string;
  created_at: string;
  calculation: EmissionCalculation | null;
}

export interface ProductConsumptionSnapshot {
  id: number;
  name: string;
  barcode: string | null;
  consumption_unit: string;
  consumption_source_type: SourceType;
  emissions_value: string;
  emissions_unit: string;
  emissions_description: string;
  source_reference: string;
}

export type ConsumptionRecordCreateRequest = {
  facility_id: number;
  quantity_consumed: string;
  unit: string;
  recorded_at: string;
} & (
  | { emission_source_id: number; product_id?: never }
  | { product_id: number; emission_source_id?: never }
);
