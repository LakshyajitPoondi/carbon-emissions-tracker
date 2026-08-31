import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { apiClient } from "../api";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { useAppState } from "../context/AppStateContext";
import type { EmissionSource, Facility, JoinRequest, SourceType } from "../types";
import { hasOrganizationWriteAccess } from "../utils/organizationRoles";
import { GHG_SCOPE_SOURCE_TYPES, sourceTypeDisplayLabel } from "../utils/sourceTypePresentation";

type ListStatus = "loading" | "ready" | "error";

export function SetupPage() {
  const { organization, facility, selectFacility } = useAppState();
  const canManageOrganization = hasOrganizationWriteAccess(organization?.role);

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
          canManage={canManageOrganization}
        />
      )}
      {organization && facility && (
        <EmissionSourceSection
          facilityId={facility.id}
          canManage={canManageOrganization}
        />
      )}
    </main>
  );
}

// ---------------------------------------------------------------------------
// Organizations — GET /organizations is the source of truth for discovery.
// AppStateContext reconciles any persisted selection against that list, so a
// second user on the same browser never inherits the first user's selection.
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

  const [joinCode, setJoinCode] = useState("");
  const [joining, setJoining] = useState(false);
  const [joinError, setJoinError] = useState<unknown>(null);
  const [pendingRequests, setPendingRequests] = useState<JoinRequest[]>([]);
  const [pendingLoading, setPendingLoading] = useState(true);

  const loadPendingRequests = useCallback(async () => {
    setPendingLoading(true);
    try {
      setPendingRequests(await apiClient.listMyPendingJoinRequests());
    } catch (err) {
      setJoinError(err);
    } finally {
      setPendingLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPendingRequests();
  }, [loadPendingRequests]);

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

  async function handleJoin(e: FormEvent) {
    e.preventDefault();
    setJoining(true);
    setJoinError(null);
    try {
      const request = await apiClient.submitJoinRequest({ join_code: joinCode });
      setPendingRequests((current) => [request, ...current]);
      setJoinCode("");
    } catch (err) {
      setJoinError(err);
    } finally {
      setJoining(false);
    }
  }

  async function checkMembershipStatus() {
    revalidateOrganizations();
    await loadPendingRequests();
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
          You don&rsquo;t have any organizations yet. Create one or request to join an existing
          organization below.
        </p>
      )}

      {!pendingLoading && pendingRequests.length > 0 && (
        <div className="result-panel">
          <h3>Pending approval</h3>
          <p className="result-panel__meta">
            Your request grants no access until an OWNER or ADMIN approves it.
          </p>
          <ul className="plain-list">
            {pendingRequests.map((request) => (
              <li key={request.id}>
                <strong>{request.organization_name}</strong> — requested {new Date(request.requested_at).toLocaleString()}
              </li>
            ))}
          </ul>
          <button type="button" onClick={() => void checkMembershipStatus()}>
            Check approval status
          </button>
        </div>
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

        <form className="card__col" onSubmit={handleJoin}>
          <h3>Join an organization</h3>
          <p className="result-panel__meta">
            Ask an OWNER or ADMIN for their organization&rsquo;s private join code. They will choose
            your role when approving the request.
          </p>
          <div className="field">
            <label htmlFor="org-join-code">Join code</label>
            <input
              id="org-join-code"
              value={joinCode}
              onChange={(e) => setJoinCode(e.target.value)}
              required
              autoComplete="off"
              placeholder="ORG-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX"
            />
          </div>
          <button type="submit" disabled={joining}>
            {joining ? "Submitting…" : "Request to join"}
          </button>
          {joinError !== null && <ErrorBanner error={joinError} />}
        </form>
      </div>

      {organization && (
        <p className="selection-confirm">
          Selected: <strong>{organization.name}</strong> ({organization.industry_type}) — Role:{" "}
          {organization.role}
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
  canManage,
}: {
  organizationId: number;
  facility: Facility | null;
  onSelect: (facility: Facility | null) => void;
  canManage: boolean;
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
            <p className="empty-state">
              {canManage
                ? "No facilities yet — create the first one below."
                : "No facilities have been created for this organization."}
            </p>
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

      {canManage ? (
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
      ) : (
        <p className="result-panel__meta">
          EMPLOYEE access is read-only here; OWNER or ADMIN is required to create facilities.
        </p>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Emission Sources
// ---------------------------------------------------------------------------

function EmissionSourceSection({
  facilityId,
  canManage,
}: {
  facilityId: number;
  canManage: boolean;
}) {
  const [sources, setSources] = useState<EmissionSource[]>([]);
  const [status, setStatus] = useState<ListStatus>("loading");
  const [listError, setListError] = useState<unknown>(null);

  const [sourceType, setSourceType] = useState<SourceType>("ENERGY");
  const [sourceName, setSourceName] = useState("");
  const [unit, setUnit] = useState("");
  const [barcodeValue, setBarcodeValue] = useState("");
  const [editingSource, setEditingSource] = useState<EmissionSource | null>(null);
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

  function resetForm() {
    setEditingSource(null);
    setSourceType("ENERGY");
    setSourceName("");
    setUnit("");
    setBarcodeValue("");
    setCreateError(null);
  }

  function beginEdit(source: EmissionSource) {
    setEditingSource(source);
    setSourceType(source.source_type);
    setSourceName(source.source_name);
    setUnit(source.unit_of_measurement);
    setBarcodeValue(source.barcode_value ?? "");
    setCreateError(null);
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      const fields = {
        source_type: sourceType,
        source_name: sourceName,
        unit_of_measurement: unit,
        barcode_value: barcodeValue.trim() || null,
      };
      if (editingSource) {
        await apiClient.updateEmissionSource(editingSource.id, fields);
      } else {
        await apiClient.createEmissionSource({ facility_id: facilityId, ...fields });
      }
      resetForm();
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
          <p className="empty-state">
            {canManage
              ? "No emission sources yet — create the first one below."
              : "No emission sources have been created for this facility."}
          </p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">GHG Protocol category</th>
                <th scope="col">Unit</th>
                <th scope="col">Barcode</th>
                {canManage && <th scope="col">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.id}>
                  <td>{s.source_name}</td>
                  <td>{sourceTypeDisplayLabel(s.source_type)}</td>
                  <td>{s.unit_of_measurement}</td>
                  <td>{s.barcode_value ?? "Not assigned"}</td>
                  {canManage && (
                    <td>
                      <button type="button" onClick={() => beginEdit(s)}>
                        Edit
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        ))}

      {canManage ? (
        <form className="card__col" onSubmit={handleCreate}>
          <h3>{editingSource ? `Edit ${editingSource.source_name}` : "Create new"}</h3>
          <div className="field">
            <label htmlFor="source-type">GHG Protocol category</label>
            <select
              id="source-type"
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value as SourceType)}
            >
              {GHG_SCOPE_SOURCE_TYPES.map((type) => (
                <option key={type} value={type}>
                  {sourceTypeDisplayLabel(type)}
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
          <div className="field">
            <label htmlFor="source-barcode">Barcode (optional)</label>
            <input
              id="source-barcode"
              value={barcodeValue}
              onChange={(e) => setBarcodeValue(e.target.value)}
              placeholder="ENSRC-00042"
            />
          </div>
          <div className="button-row">
            <button type="submit" disabled={creating}>
              {creating
                ? "Saving…"
                : editingSource
                  ? "Save changes"
                  : "Create emission source"}
            </button>
            {editingSource && (
              <button type="button" className="link-button" onClick={resetForm}>
                Cancel edit
              </button>
            )}
          </div>
          {createError !== null && <ErrorBanner error={createError} />}
        </form>
      ) : (
        <p className="result-panel__meta">
          EMPLOYEE access is read-only here; OWNER or ADMIN is required to create emission sources.
        </p>
      )}
    </section>
  );
}
