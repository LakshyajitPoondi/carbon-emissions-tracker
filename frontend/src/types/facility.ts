/** Mirrors docs/api-contract.md — Facilities section. */

export interface Facility {
  id: number;
  organization_id: number;
  name: string;
  location: string;
  facility_type: string;
  created_at: string;
  updated_at: string;
}

export interface FacilityCreateRequest {
  organization_id: number;
  name: string;
  location: string;
  facility_type: string;
}
