/** Mirrors docs/api-contract.md — Organizations section. */

export type OrganizationRole = "OWNER" | "ADMIN" | "EMPLOYEE";

export interface Organization {
  id: number;
  name: string;
  industry_type: string;
  created_at: string;
  /** The current user's role in this organization. */
  role: OrganizationRole;
}

export interface OrganizationCreateRequest {
  name: string;
  industry_type: string;
}
