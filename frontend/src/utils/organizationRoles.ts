import type { OrganizationRole } from "../types";

/** UI convenience only; backend authorization remains the security boundary. */
export function hasOrganizationWriteAccess(
  role: OrganizationRole | undefined,
): boolean {
  return role === "OWNER" || role === "ADMIN";
}
