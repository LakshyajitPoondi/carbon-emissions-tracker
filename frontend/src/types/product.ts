/** Mirrors Docs/api-contract.md — Product Library. */

export interface Product {
  id: number;
  organization_id: number;
  name: string;
  barcode: string | null;
  composition: string;
  emissions_value: string;
  emissions_unit: string;
  emissions_description: string;
  source_reference: string;
  created_at: string;
  updated_at: string;
}

export interface ProductCreateRequest {
  organization_id: number;
  name: string;
  barcode?: string | null;
  composition: string;
  emissions_value: string;
  emissions_unit: string;
  emissions_description: string;
  source_reference: string;
}

export interface ProductUpdateRequest {
  name?: string;
  barcode?: string | null;
  composition?: string;
  emissions_value?: string;
  emissions_unit?: string;
  emissions_description?: string;
  source_reference?: string;
}
