import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { apiClient } from "../api";
import type { Facility, Organization } from "../types";
import { useAuth } from "./AuthContext";

const STORAGE_KEY = "cfp.selection";

/** Retired: this browser used to cache organization ids for discovery, back
 * when the API had no list endpoint. GET /organizations replaced it, so the
 * key is purged on load rather than left to rot in returning users' storage. */
const LEGACY_KNOWN_ORGS_KEY = "cfp.knownOrganizations";

interface StoredSelection {
  organization: Organization | null;
  facility: Facility | null;
}

function loadStoredSelection(): StoredSelection {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { organization: null, facility: null };
    const parsed = JSON.parse(raw) as StoredSelection;
    return { organization: parsed.organization ?? null, facility: parsed.facility ?? null };
  } catch {
    return { organization: null, facility: null };
  }
}

function clearStoredSelection(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

function purgeLegacyKeys(): void {
  try {
    localStorage.removeItem(LEGACY_KNOWN_ORGS_KEY);
  } catch {
    // ignore
  }
}

export type OrganizationsStatus = "idle" | "loading" | "ready" | "error";

interface AppState {
  organization: Organization | null;
  facility: Facility | null;
  /** The user's organizations, straight from GET /organizations. */
  organizations: Organization[];
  organizationsStatus: OrganizationsStatus;
  organizationsError: unknown;
  selectOrganization: (organization: Organization | null) => void;
  selectFacility: (facility: Facility | null) => void;
  /** Add a just-created organization to the list without a refetch. */
  rememberOrganization: (organization: Organization) => void;
  revalidateOrganizations: () => void;
}

const AppStateContext = createContext<AppState | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();

  const [organization, setOrganization] = useState<Organization | null>(
    () => loadStoredSelection().organization,
  );
  const [facility, setFacility] = useState<Facility | null>(() => loadStoredSelection().facility);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [organizationsStatus, setOrganizationsStatus] = useState<OrganizationsStatus>("idle");
  const [organizationsError, setOrganizationsError] = useState<unknown>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  // Lets the fetch effect read the current selection without depending on it,
  // which would restart the fetch every time the user picks an organization.
  const organizationRef = useRef(organization);
  useEffect(() => {
    organizationRef.current = organization;
  }, [organization]);

  useEffect(() => {
    purgeLegacyKeys();
  }, []);

  // Persist the selection — but only the *selection*. Which organizations
  // exist is the server's business now; this is purely so a page reload does
  // not dump the user back to "nothing selected".
  useEffect(() => {
    if (!isAuthenticated) return;
    try {
      const selection: StoredSelection = { organization, facility };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(selection));
    } catch {
      // ignore
    }
  }, [organization, facility, isAuthenticated]);

  // ---------------------------------------------------------------------
  // Cross-account hygiene. Hooked to isAuthenticated rather than to the
  // log-out button, so it also covers a session ending because a token
  // expired: a 401 fires UNAUTHORIZED_EVENT, AuthContext drops the token,
  // and this runs for free.
  // ---------------------------------------------------------------------
  useEffect(() => {
    if (isAuthenticated) return;
    setOrganization(null);
    setFacility(null);
    setOrganizations([]);
    setOrganizationsStatus("idle");
    setOrganizationsError(null);
    clearStoredSelection();
  }, [isAuthenticated]);

  // ---------------------------------------------------------------------
  // Load the user's organizations from the server on login and app load.
  //
  // The server is the only source of discovery, so this works on a browser
  // with no stored state at all — which is what makes a returning user on a
  // new machine see their real organizations instead of a false empty state.
  //
  // A stored selection is still reconciled against the response: it is a
  // convenience carried across reloads, not evidence of access, and after an
  // account switch it may name an organization this user cannot see.
  // ---------------------------------------------------------------------
  useEffect(() => {
    if (!isAuthenticated) return;

    let cancelled = false;

    async function load() {
      setOrganizationsStatus("loading");
      setOrganizationsError(null);
      try {
        const orgs = await apiClient.listOrganizations();
        if (cancelled) return;

        setOrganizations(orgs);
        setOrganizationsStatus("ready");

        const selected = organizationRef.current;
        if (selected) {
          // Prefer the server's copy — a cached name may be out of date.
          const confirmed = orgs.find((o) => o.id === selected.id) ?? null;
          setOrganization(confirmed);
          if (!confirmed) setFacility(null);
        }
      } catch (err) {
        if (cancelled) return;
        setOrganizationsError(err);
        setOrganizationsStatus("error");
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, reloadNonce]);

  const selectOrganization = useCallback((next: Organization | null) => {
    setOrganization(next);
    // A facility belongs to exactly one organization — switching orgs (or
    // clearing the selection) invalidates whichever facility was picked.
    setFacility(null);
  }, []);

  const selectFacility = useCallback((next: Facility | null) => {
    setFacility(next);
  }, []);

  const rememberOrganization = useCallback((next: Organization) => {
    // In-memory only. Nothing is written to storage: this just saves a
    // refetch after POST /organizations, and the server's own ordering is
    // mirrored so the new entry lands where the next load will put it.
    setOrganizations((current) =>
      [...current.filter((o) => o.id !== next.id), next].sort(
        (a, b) => a.name.localeCompare(b.name) || a.id - b.id,
      ),
    );
  }, []);

  const revalidateOrganizations = useCallback(() => {
    setReloadNonce((n) => n + 1);
  }, []);

  return (
    <AppStateContext.Provider
      value={{
        organization,
        facility,
        organizations,
        organizationsStatus,
        organizationsError,
        selectOrganization,
        selectFacility,
        rememberOrganization,
        revalidateOrganizations,
      }}
    >
      {children}
    </AppStateContext.Provider>
  );
}

export function useAppState(): AppState {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error("useAppState must be used within an AppStateProvider");
  return ctx;
}
