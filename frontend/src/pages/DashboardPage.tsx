import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "../api";
import { DateRangeFilter } from "../components/DateRangeFilter";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { useAppState } from "../context/AppStateContext";
import { useFacilityLiveUpdates } from "../hooks/useFacilityLiveUpdates";
import type { ConsumptionRecord, EmissionsSummary } from "../types";
import { daysAgoInputValue, formatKgCo2e, todayInputValue } from "../utils/format";
import { GHG_SCOPE_SOURCE_TYPES, sourceTypeDisplayLabel } from "../utils/sourceTypePresentation";

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
    summary != null
      ? Math.max(1, ...GHG_SCOPE_SOURCE_TYPES.map((type) => Number(summary.by_source_type[type])))
      : 1;

  return (
    <main className="page">
      <h1>Dashboard</h1>
      <p className="page__intro">
        GHG Protocol emissions summary for <strong>{facilityName}</strong>.
        {isLive && (
          <span className="live-badge" title="Live updates connected">
            <span className="live-badge__dot" aria-hidden="true" /> Live
          </span>
        )}
      </p>

      <DateRangeFilter
        idPrefix="dashboard"
        startDate={startDate}
        endDate={endDate}
        onStartDateChange={setStartDate}
        onEndDateChange={setEndDate}
        onSubmit={handleSubmit}
        loading={status === "loading"}
      />

      {status === "loading" && <LoadingState label="Calculating emissions summary…" />}
      {status === "error" && <ErrorBanner error={error} onRetry={load} />}

      {status === "ready" && summary && (
        <section className="card">
          <h2>Scope 1, 2 &amp; 3 emissions</h2>
          <p className="result-panel__figure">
            {formatKgCo2e(summary.total_emissions_kg_co2e)} kg CO2e
            <span className="result-panel__meta">
              {" "}
              combined total, {summary.period.start} – {summary.period.end}
            </span>
          </p>

          <div className="bar-chart" role="img" aria-label="GHG emissions by scope">
            {GHG_SCOPE_SOURCE_TYPES.map((type) => {
              const value = Number(summary.by_source_type[type]);
              const widthPct = (value / maxValue) * 100;
              return (
                <div className="bar-chart__row" key={type}>
                  <span className="bar-chart__label">{sourceTypeDisplayLabel(type)}</span>
                  <div className="bar-chart__track">
                    <div
                      className={`bar-chart__fill bar-chart__fill--${type.toLowerCase()}`}
                      style={{ width: `${widthPct}%` }}
                    />
                  </div>
                  <span className="bar-chart__value">
                    {formatKgCo2e(summary.by_source_type[type])} kg CO2e
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </main>
  );
}
