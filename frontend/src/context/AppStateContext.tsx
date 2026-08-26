import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import type { Facility, Organization } from "../types";

const STORAGE_KEY = "cfp.selection";

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

interface AppState {
  organization: Organization | null;
  facility: Facility | null;
  selectOrganization: (organization: Organization | null) => void;
  selectFacility: (facility: Facility | null) => void;
}

const AppStateContext = createContext<AppState | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [organization, setOrganization] = useState<Organization | null>(
    () => loadStoredSelection().organization,
  );
  const [facility, setFacility] = useState<Facility | null>(() => loadStoredSelection().facility);

  useEffect(() => {
    const selection: StoredSelection = { organization, facility };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(selection));
  }, [organization, facility]);

  const selectOrganization = useCallback((next: Organization | null) => {
    setOrganization(next);
    // A facility belongs to exactly one organization — switching orgs (or
    // clearing the selection) invalidates whichever facility was picked.
    setFacility(null);
  }, []);

  const selectFacility = useCallback((next: Facility | null) => {
    setFacility(next);
  }, []);

  return (
    <AppStateContext.Provider value={{ organization, facility, selectOrganization, selectFacility }}>
      {children}
    </AppStateContext.Provider>
  );
}

export function useAppState(): AppState {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error("useAppState must be used within an AppStateProvider");
  return ctx;
}
