import type { OrganizationRole } from "./organization";

export type JoinRequestStatus = "PENDING" | "APPROVED" | "REJECTED";

export interface JoinCode {
  organization_id: number;
  join_code: string;
}

export interface JoinRequest {
  id: number;
  organization_id: number;
  organization_name: string;
  user_id: number;
  user_email: string;
  status: JoinRequestStatus;
  requested_at: string;
  decided_at: string | null;
  decided_by: number | null;
}

export interface OrganizationMember {
  user_id: number;
  email: string;
  role: OrganizationRole;
  joined_at: string;
}

export interface JoinRequestCreateRequest {
  join_code: string;
}

export interface JoinRequestApprovalRequest {
  role: OrganizationRole;
}

export interface MemberRoleUpdateRequest {
  role: OrganizationRole;
}

