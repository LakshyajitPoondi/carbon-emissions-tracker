import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { apiClient } from "../api";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { useAppState } from "../context/AppStateContext";
import type { EmissionSource, Facility, SourceType } from "../types";
import { SOURCE_TYPES } from "../types";

type ListStatus = "loading" | "ready" | "error";

export function SetupPage() {
  const { organization, facility, selectFacility } = useAppState();

  return (
    <main className="page">
      <h1>Setup</h1>
      <p className="page__intro">
        Pick or create an organization, then a facility, then the emission sources it tracks. Once a
        facility is selected here, the Consumption, Dashboard and Reports screens use it automatically.
      </p>
      <OrganizationSection />
      {organization && (
        <FacilitySection
          organizationId={organization.id}
          facility={facility}
          onSelect={selectFacility}
        />
      )}
      {organization && facility && <EmissionSourceSection facilityId={facility.id} />}
    </main>
  );
}

// ---------------------------------------------------------------------------
// Organizations — the contract still has no list endpoint, so the picker is
// built from this browser's cache of organizations it has created or looked
// up. Since the backend gained membership authorization, that cache is
// revalidated against the server before it is shown (see AppStateContext):
// anything this user cannot actually access is dropped, so a second user on
// the same browser never sees the first user's organizations.
// ---------------------------------------------------------------------------

function OrganizationSection() {
  const {
    organization,
    organizations: known,
    organizationsStatus,
    organizationsError,
    selectOrganization: onSelect,
    rememberOrganization,
    revalidateOrganizations,
  } = useAppState();

  const [name, setName] = useState("");
  const [industryType, setIndustryType] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<unknown>(null);

  const [lookupId, setLookupId] = useState("");
  const [lookingUp, setLookingUp] = useState(false);
  const [lookupError, setLookupError] = useState<unknown>(null);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      const org = await apiClient.createOrganization({ name, industry_type: industryType });
      rememberOrganization(org);
      onSelect(org);
      setName("");
      setIndustryType("");
    } catch (err) {
      setCreateError(err);
    } finally {
      setCreating(false);
    }
  }

  async function handleLookup(e: FormEvent) {
    e.preventDefault();
    const id = Number(lookupId);
    if (!Number.isFinite(id) || id <= 0) {
      setLookupError(new Error("Enter a valid organization ID."));
      return;
    }
    setLookingUp(true);
    setLookupError(null);
    try {
      const org = await apiClient.getOrganization(id);
      rememberOrganization(org);
      onSelect(org);
      setLookupId("");
    } catch (err) {
      setLookupError(err);
    } finally {
      setLookingUp(false);
    }
  }

  return (
    <section className="card">
      <h2>1. Organization</h2>

      {organizationsStatus === "loading" && (
        <LoadingState label="Loading your organizations…" />
      )}

      {organizationsStatus === "error" && (
        <ErrorBanner error={organizationsError} onRetry={revalidateOrganizations} />
      )}

      {organizationsStatus === "ready" && known.length === 0 && (
        <p className="empty-state">
          You don&rsquo;t have any organizations yet — create one below to get started.
        </p>
      )}

      {known.length > 0 && (
        <div className="field">
          <label htmlFor="your-org-select">Your organizations</label>
          <select
            id="your-org-select"
            value={organization?.id ?? ""}
            onChange={(e) => {
              const id = Number(e.target.value);
              onSelect(known.find((o) => o.id === id) ?? null);
            }}
          >
            <option value="">— none selected —</option>
            {known.map((org) => (
              <option key={org.id} value={org.id}>
                {org.name} (#{org.id})
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="card__row">
        <form className="card__col" onSubmit={handleCreate}>
          <h3>Create new</h3>
          <div className="field">
            <label htmlFor="org-name">Name</label>
            <input
              id="org-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              placeholder="Acme Manufacturing"
            />
          </div>
          <div className="field">
            <label htmlFor="org-industry">Industry type</label>
            <input
              id="org-industry"
              value={industryType}
              onChange={(e) => setIndustryType(e.target.value)}
              required
              placeholder="manufacturing"
            />
          </div>
          <button type="submit" disabled={creating}>
            {creating ? "Creating…" : "Create organization"}
          </button>
          {createError !== null && <ErrorBanner error={createError} />}
        </form>

        <form className="card__col" onSubmit={handleLookup}>
          <h3>Load existing by ID</h3>
          <div className="field">
            <label htmlFor="org-lookup">Organization ID</label>
            <input
              id="org-lookup"
              type="number"
              min={1}
              value={lookupId}
              onChange={(e) => setLookupId(e.target.value)}
              placeholder="1"
            />
          </div>
          <button type="submit" disabled={lookingUp}>
            {lookingUp ? "Looking up…" : "Load organization"}
          </button>
          {lookupError !== null && <ErrorBanner error={lookupError} />}
        </form>
      </div>

      {organization && (
        <p className="selection-confirm">
          Selected: <strong>{organization.name}</strong> ({organization.industry_type})
        </p>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Facilities — GET /facilities?organization_id={id} does exist, so this
// section lists real data from the server.
// ---------------------------------------------------------------------------

function FacilitySection({
  organizationId,
  facility,
  onSelect,
}: {
  organizationId: number;
  facility: Facility | null;
  onSelect: (facility: Facility | null) => void;
}) {
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [status, setStatus] = useState<ListStatus>("loading");
  const [listError, setListError] = useState<unknown>(null);

  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [facilityType, setFacilityType] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setListError(null);
    try {
      const data = await apiClient.listFacilities(organizationId);
      setFacilities(data);
      setStatus("ready");
    } catch (err) {
      setListError(err);
      setStatus("error");
    }
  }, [organizationId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      const created = await apiClient.createFacility({
        organization_id: organizationId,
        name,
        location,
        facility_type: facilityType,
      });
      setName("");
      setLocation("");
      setFacilityType("");
      await load();
      onSelect(created);
    } catch (err) {
      setCreateError(err);
    } finally {
      setCreating(false);
    }
  }

  return (
    <section className="card">
      <h2>2. Facility</h2>

      {status === "loading" && <LoadingState label="Loading facilities…" />}
      {status === "error" && <ErrorBanner error={listError} onRetry={load} />}
      {status === "ready" && (
        <>
          {facilities.length === 0 ? (
            <p className="empty-state">No facilities yet — create the first one below.</p>
          ) : (
            <ul className="pick-list">
              {facilities.map((f) => (
                <li key={f.id}>
                  <button
                    type="button"
                    className={f.id === facility?.id ? "pick-list__item pick-list__item--active" : "pick-list__item"}
                    onClick={() => onSelect(f)}
                  >
                    <strong>{f.name}</strong> — {f.location} ({f.facility_type})
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      <form className="card__col" onSubmit={handleCreate}>
        <h3>Create new</h3>
        <div className="field">
          <label htmlFor="fac-name">Name</label>
          <input id="fac-name" value={name} onChange={(e) => setName(e.target.value)} required placeholder="Chennai Plant" />
        </div>
        <div className="field">
          <label htmlFor="fac-location">Location</label>
          <input
            id="fac-location"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            required
            placeholder="Chennai, TN"
          />
        </div>
        <div className="field">
          <label htmlFor="fac-type">Facility type</label>
          <input
            id="fac-type"
            value={facilityType}
            onChange={(e) => setFacilityType(e.target.value)}
            required
            placeholder="factory"
          />
        </div>
        <button type="submit" disabled={creating}>
          {creating ? "Creating…" : "Create facility"}
        </button>
        {createError !== null && <ErrorBanner error={createError} />}
      </form>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Emission Sources
// ---------------------------------------------------------------------------

function EmissionSourceSection({ facilityId }: { facilityId: number }) {
  const [sources, setSources] = useState<EmissionSource[]>([]);
  const [status, setStatus] = useState<ListStatus>("loading");
  const [listError, setListError] = useState<unknown>(null);

  const [sourceType, setSourceType] = useState<SourceType>("ENERGY");
  const [sourceName, setSourceName] = useState("");
  const [unit, setUnit] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setListError(null);
    try {
      const data = await apiClient.listEmissionSources(facilityId);
      setSources(data);
      setStatus("ready");
    } catch (err) {
      setListError(err);
      setStatus("error");
    }
  }, [facilityId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      await apiClient.createEmissionSource({
        facility_id: facilityId,
        source_type: sourceType,
        source_name: sourceName,
        unit_of_measurement: unit,
      });
      setSourceName("");
      setUnit("");
      await load();
    } catch (err) {
      setCreateError(err);
    } finally {
      setCreating(false);
    }
  }

  return (
    <section className="card">
      <h2>3. Emission Sources</h2>

      {status === "loading" && <LoadingState label="Loading emission sources…" />}
      {status === "error" && <ErrorBanner error={listError} onRetry={load} />}
      {status === "ready" &&
        (sources.length === 0 ? (
          <p className="empty-state">No emission sources yet — create the first one below.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Type</th>
                <th scope="col">Unit</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.id}>
                  <td>{s.source_name}</td>
                  <td>{s.source_type}</td>
                  <td>{s.unit_of_measurement}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}

      <form className="card__col" onSubmit={handleCreate}>
        <h3>Create new</h3>
        <div className="field">
          <label htmlFor="source-type">Source type</label>
          <select
            id="source-type"
            value={sourceType}
            onChange={(e) => setSourceType(e.target.value as SourceType)}
          >
            {SOURCE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="source-name">Source name</label>
          <input
            id="source-name"
            value={sourceName}
            onChange={(e) => setSourceName(e.target.value)}
            required
            placeholder="Grid electricity"
          />
        </div>
        <div className="field">
          <label htmlFor="source-unit">Unit of measurement</label>
          <input
            id="source-unit"
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
            required
            placeholder="kWh"
          />
        </div>
        <button type="submit" disabled={creating}>
          {creating ? "Creating…" : "Create emission source"}
        </button>
        {createError !== null && <ErrorBanner error={createError} />}
      </form>
    </section>
  );
}
