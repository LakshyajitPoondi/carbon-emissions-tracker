/**
 * The contract has no "list organizations" endpoint (only POST /organizations
 * and GET /organizations/{id}), so there is no server-side way to populate an
 * organization picker. This keeps a small client-side memory of organizations
 * this browser has created or looked up, purely as a UX convenience — it is
 * not a substitute for real persistence and is never treated as a source of
 * truth (every selection is still backed by a real id the server issued).
 */

import type { Organization } from "../types";

const KEY = "cfp.knownOrganizations";

export function loadKnownOrganizations(): Organization[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    return JSON.parse(raw) as Organization[];
  } catch {
    return [];
  }
}

export function rememberOrganization(org: Organization): Organization[] {
  const next = [...loadKnownOrganizations().filter((o) => o.id !== org.id), org].sort(
    (a, b) => a.id - b.id,
  );
  localStorage.setItem(KEY, JSON.stringify(next));
  return next;
}
