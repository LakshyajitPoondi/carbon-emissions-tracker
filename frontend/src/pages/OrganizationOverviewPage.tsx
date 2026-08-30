import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "../api";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { useAppState } from "../context/AppStateContext";
import type { OrganizationOverview, SourceType } from "../types";
import { SOURCE_TYPES } from "../types";
import { daysAgoInputValue, formatKgCo2e, todayInputValue } from "../utils/format";

const SOURCE_TYPE_LABEL: Record<SourceType, string> = {
  ENERGY: "Energy",
  FUEL: "Fuel",
  RESOURCE: "Resource",
};

/**
 * Every facility in the current organization, side by side, from a single
 * GraphQL request.
 *
 * This is the read-only counterpart to the Dashboard: that screen answers
 * "how is this one facility doing", using REST. This one answers "how does
 * the organization break down", which over REST would be 1 + N calls — the
 * organization, then a summary per facility. GraphQL resolves it in one
 * round trip, and the backend batches the per-facility summaries with a
 * DataLoader so it is also one grouped query on the server rather than N.
 *
 * The numbers are the same numbers: the resolver calls the identical
 * service function that GET /facilities/{id}/emissions-summary uses. This
 * page is a second *view*, never a second source of truth.
 */
export function OrganizationOverviewPage() {
  const { organization } = useAppState();

  if (!organization) {
    return (
      <main className="page">
        <h1>Organization Overview</h1>
        <p className="empty-state">
          Select an organization on the <Link to="/">Setup</Link> screen first.
        </p>
      </main>
    );
  }

  return <OverviewForOrganization organizationId={organization.id} />;
}

function OverviewForOrganization({ organizationId }: { organizationId: number }) {
  const [startDate, setStartDate] = useState(daysAgoInputValue(30));
  const [endDate, setEndDate] = useState(todayInputValue());
  const [overview, setOverview] = useState<OrganizationOverview | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const data = await apiClient.getOrganizationOverview(organizationId, {
        start_date: startDate,
        end_date: endDate,
      });
      setOverview(data);
      setStatus("ready");
    } catch (err) {
      setError(err);
      setStatus("error");
    }
    // startDate/endDate are read on submit, not on every keystroke — same
    // pattern as the Dashboard's filter bar.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [organizationId]);

  useEffect(() => {
    load();
  }, [load]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    load();
  }

  const facilities = overview?.facilities ?? [];

  // The schema has no organization-level total — EmissionsSummaryType is
  // per-facility only — so it is summed here. Decimals arrive as strings and
  // are summed as numbers, which is safe at this scale: the backend rounds
  // each facility to 2dp and the total is displayed at 2dp, so any float
  // representation error is orders of magnitude below the displayed digit.
  const organizationTotal = facilities.reduce(
    (sum, facility) => sum + Number(facility.emissionsSummary.totalEmissionsKgCo2e),
    0,
  );

  // Shared scale across facilities: each facility's bars are drawn relative
  // to the largest single category anywhere in the organization, so the
  // charts are comparable between facilities rather than each being
  // normalized to its own maximum (which would make a tiny facility look
  // identical to the biggest one).
  const maxCategoryValue = Math.max(
    1,
    ...facilities.flatMap((facility) =>
      SOURCE_TYPES.map((type) => Number(facility.emissionsSummary.bySourceType[type] ?? 0)),
    ),
  );

  return (
    <main className="page">
      <h1>{overview ? overview.name : "Organization Overview"}</h1>
      <p className="page__intro">
        Every facility in this organization, from a single GraphQL query.
        {overview && <span className="result-panel__meta"> {overview.industryType}</span>}
      </p>

      <form className="filter-bar" onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="overview-start">Start date</label>
          <input
            id="overview-start"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="overview-end">End date</label>
          <input
            id="overview-end"
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            required
          />
        </div>
        <button type="submit" disabled={status === "loading"}>
          {status === "loading" ? "Loading…" : "View"}
        </button>
      </form>

      {status === "loading" && <LoadingState label="Loading organization overview…" />}
      {status === "error" && <ErrorBanner error={error} onRetry={load} />}

      {status === "ready" && overview && (
        <>
          <section className="card">
            <p className="result-panel__figure">
              {formatKgCo2e(String(organizationTotal))} kg CO2e
              <span className="result-panel__meta">
                {" "}
                organization total, {startDate} – {endDate}
              </span>
            </p>
            <p className="result-panel__meta">
              Summed across {facilities.length}{" "}
              {facilities.length === 1 ? "facility" : "facilities"}.
            </p>
          </section>

          {facilities.length === 0 ? (
            <p className="empty-state">
              This organization has no facilities yet — add one on the{" "}
              <Link to="/">Setup</Link> screen, and its emissions will appear here.
            </p>
          ) : (
            facilities.map((facility) => {
              const summary = facility.emissionsSummary;
              return (
                <section className="card" key={facility.id}>
                  <h2>{facility.name}</h2>
                  <p className="result-panel__figure">
                    {formatKgCo2e(summary.totalEmissionsKgCo2e)} kg CO2e
                    <span className="result-panel__meta"> {facility.location}</span>
                  </p>

                  <div
                    className="bar-chart"
                    role="img"
                    aria-label={`Emissions by source type for ${facility.name}`}
                  >
                    {SOURCE_TYPES.map((type) => {
                      const raw = summary.bySourceType[type] ?? "0";
                      const value = Number(raw);
                      const widthPct = (value / maxCategoryValue) * 100;
                      return (
                        <div className="bar-chart__row" key={type}>
                          <span className="bar-chart__label">{SOURCE_TYPE_LABEL[type]}</span>
                          <div className="bar-chart__track">
                            <div
                              className={`bar-chart__fill bar-chart__fill--${type.toLowerCase()}`}
                              style={{ width: `${widthPct}%` }}
                            />
                          </div>
                          <span className="bar-chart__value">{formatKgCo2e(raw)} kg</span>
                        </div>
                      );
                    })}
                  </div>
                </section>
              );
            })
          )}
        </>
      )}
    </main>
  );
}
