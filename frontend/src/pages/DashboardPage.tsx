import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "../api";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { useAppState } from "../context/AppStateContext";
import { useFacilityLiveUpdates } from "../hooks/useFacilityLiveUpdates";
import type { ConsumptionRecord, EmissionsSummary, SourceType } from "../types";
import { SOURCE_TYPES } from "../types";
import { daysAgoInputValue, formatKgCo2e, todayInputValue } from "../utils/format";

const SOURCE_TYPE_LABEL: Record<SourceType, string> = {
  ENERGY: "Energy",
  FUEL: "Fuel",
  RESOURCE: "Resource",
};

export function DashboardPage() {
  const { facility } = useAppState();

  if (!facility) {
    return (
      <main className="page">
        <h1>Dashboard</h1>
        <p className="empty-state">
          Select a facility on the <Link to="/">Setup</Link> screen first.
        </p>
      </main>
    );
  }

  return <DashboardForFacility facilityId={facility.id} facilityName={facility.name} />;
}

function DashboardForFacility({ facilityId, facilityName }: { facilityId: number; facilityName: string }) {
  const [startDate, setStartDate] = useState(daysAgoInputValue(30));
  const [endDate, setEndDate] = useState(todayInputValue());
  const [summary, setSummary] = useState<EmissionsSummary | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const data = await apiClient.getEmissionsSummary(facilityId, {
        start_date: startDate,
        end_date: endDate,
      });
      setSummary(data);
      setStatus("ready");
    } catch (err) {
      setError(err);
      setStatus("error");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [facilityId]);

  useEffect(() => {
    load();
  }, [load]);

  // Live updates: on a broadcast, refetch the summary rather than trying to
  // merge the new record into the totals locally. Merging would require
  // knowing the new record's source_type to add it to the right bucket, but
  // the broadcast payload only carries emission_source_id (see
  // docs/api-contract.md) and this screen doesn't otherwise load the
  // emission-source list — fetching it just to enable a client-side
  // arithmetic shortcut adds a new failure mode (a stale/missing id->type
  // mapping) for a marginal gain over reusing the exact same `load()` this
  // screen's manual "View" button already calls, which is simpler and
  // provably consistent with the backend's own rounding. Only refetch when
  // the new record actually falls inside the currently-viewed period —
  // otherwise the displayed numbers are already correct as-is and
  // refetching would just be a pointless network call.
  const handleRecordCreated = useCallback(
    (record: ConsumptionRecord) => {
      const recordDate = record.recorded_at.slice(0, 10);
      if (recordDate >= startDate && recordDate <= endDate) {
        load();
      }
    },
    [startDate, endDate, load],
  );
  const isLive = useFacilityLiveUpdates(facilityId, handleRecordCreated);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    load();
  }

  const maxValue =
    summary != null ? Math.max(1, ...SOURCE_TYPES.map((t) => Number(summary.by_source_type[t]))) : 1;

  return (
    <main className="page">
      <h1>Dashboard</h1>
      <p className="page__intro">
        Emissions summary for <strong>{facilityName}</strong>.
        {isLive && (
          <span className="live-badge" title="Live updates connected">
            <span className="live-badge__dot" aria-hidden="true" /> Live
          </span>
        )}
      </p>

      <form className="filter-bar" onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="dashboard-start">Start date</label>
          <input
            id="dashboard-start"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="dashboard-end">End date</label>
          <input
            id="dashboard-end"
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

      {status === "loading" && <LoadingState label="Calculating emissions summary…" />}
      {status === "error" && <ErrorBanner error={error} onRetry={load} />}

      {status === "ready" && summary && (
        <section className="card">
          <p className="result-panel__figure">
            {formatKgCo2e(summary.total_emissions_kg_co2e)} kg CO2e
            <span className="result-panel__meta"> total, {summary.period.start} – {summary.period.end}</span>
          </p>

          <div className="bar-chart" role="img" aria-label="Emissions by source type">
            {SOURCE_TYPES.map((type) => {
              const value = Number(summary.by_source_type[type]);
              const widthPct = (value / maxValue) * 100;
              return (
                <div className="bar-chart__row" key={type}>
                  <span className="bar-chart__label">{SOURCE_TYPE_LABEL[type]}</span>
                  <div className="bar-chart__track">
                    <div
                      className={`bar-chart__fill bar-chart__fill--${type.toLowerCase()}`}
                      style={{ width: `${widthPct}%` }}
                    />
                  </div>
                  <span className="bar-chart__value">{formatKgCo2e(summary.by_source_type[type])} kg</span>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </main>
  );
}
