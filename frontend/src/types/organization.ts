/** Mirrors docs/api-contract.md — Organizations section. */

export interface Organization {
  id: number;
  name: string;
  industry_type: string;
  created_at: string;
}

export interface OrganizationCreateRequest {
  name: string;
  industry_type: string;
}
