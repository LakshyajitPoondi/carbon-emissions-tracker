import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "../api";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { useAppState } from "../context/AppStateContext";
import { useOrganizationLiveUpdates } from "../hooks/useOrganizationLiveUpdates";
import type { Report, ReportStatus, ReportSummary } from "../types";
import { daysAgoInputValue, formatDateTime, formatKgCo2e, todayInputValue } from "../utils/format";

// How often to poll GET /reports/{id} for a report that's still
// pending/processing, as a backup to the organization WebSocket channel
// (see useOrganizationLiveUpdates.ts and docs/api-contract.md's WebSocket
// section: that channel is relayed through Redis pub/sub from a separate
// celery-worker process, so it isn't guaranteed to fire — a dropped
// connection or a missed subscribe window means the push never arrives).
// Whichever source updates the report first — the WS push or the next poll
// tick — wins; the other is then just a harmless no-op.
const POLL_INTERVAL_MS = 3000;

const STATUS_LABEL: Record<ReportStatus, string> = {
  draft: "Draft",
  pending: "Pending",
  processing: "Processing",
  final: "Final",
};

function toSummary(report: Report): ReportSummary {
  return {
    id: report.id,
    organization_id: report.organization_id,
    report_period_start: report.report_period_start,
    report_period_end: report.report_period_end,
    generated_at: report.generated_at,
    status: report.status,
    total_emissions_kg_co2e: report.total_emissions_kg_co2e,
  };
}

export function ReportsPage() {
  const { organization } = useAppState();

  if (!organization) {
    return (
      <main className="page">
        <h1>Reports</h1>
        <p className="empty-state">
          Select an organization on the <Link to="/">Setup</Link> screen first.
        </p>
      </main>
    );
  }

  return <ReportsForOrganization organizationId={organization.id} organizationName={organization.name} />;
}

function ReportsForOrganization({
  organizationId,
  organizationName,
}: {
  organizationId: number;
  organizationName: string;
}) {
  const [periodStart, setPeriodStart] = useState(daysAgoInputValue(30));
  const [periodEnd, setPeriodEnd] = useState(todayInputValue());
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<unknown>(null);
  const [generated, setGenerated] = useState<Report | null>(null);

  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [listStatus, setListStatus] = useState<"loading" | "ready" | "error">("loading");
  const [listError, setListError] = useState<unknown>(null);

  const [selectedReport, setSelectedReport] = useState<Report | null>(null);
  const [detailStatus, setDetailStatus] = useState<"idle" | "loading" | "error">("idle");
  const [detailError, setDetailError] = useState<unknown>(null);

  // The id of a not-yet-final report that the backup poll (and, in
  // parallel, any WebSocket push) should keep watching until it reaches
  // "final". Only one report is actively polled at a time — whichever was
  // most recently generated or opened via "View" — which is sufficient for
  // this project's single-user-at-a-time demo scope.
  const [pendingReportId, setPendingReportId] = useState<number | null>(null);

  const loadReports = useCallback(async () => {
    setListStatus("loading");
    setListError(null);
    try {
      const data = await apiClient.listReports(organizationId);
      setReports(data);
      setListStatus("ready");
    } catch (err) {
      setListError(err);
      setListStatus("error");
    }
  }, [organizationId]);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  // Applies a fresh report snapshot (from a WS push or a poll tick)
  // everywhere it's currently displayed: the just-generated confirmation,
  // the matching list row, and the open detail panel — whichever of those
  // happen to already be showing this report's id. Stops the backup poll
  // once the report this update is for has reached "final".
  const applyReportUpdate = useCallback((report: Report) => {
    setGenerated((prev) => (prev && prev.id === report.id ? report : prev));
    setSelectedReport((prev) => (prev && prev.id === report.id ? report : prev));
    setReports((prev) => {
      const idx = prev.findIndex((r) => r.id === report.id);
      if (idx === -1) return prev;
      const next = [...prev];
      next[idx] = toSummary(report);
      return next;
    });
    setPendingReportId((prev) => (prev === report.id && report.status === "final" ? null : prev));
  }, []);

  const isLive = useOrganizationLiveUpdates(organizationId, applyReportUpdate);

  // Backup poll: while a report is pending/processing, keep checking
  // GET /reports/{id} every few seconds in case the WebSocket event never
  // arrives (connection never established, dropped mid-wait, missed the
  // pub/sub subscribe window, etc.). Stops as soon as that report reaches
  // "final" — via this poll or the WS listener, either one clears
  // pendingReportId — or a different report starts being watched instead.
  useEffect(() => {
    if (pendingReportId == null) return;
    const id = pendingReportId;
    let cancelled = false;
    const interval = window.setInterval(async () => {
      try {
        const report = await apiClient.getReport(id);
        if (!cancelled) applyReportUpdate(report);
      } catch {
        // A transient poll failure isn't worth surfacing as a page-level
        // error banner — the next tick, or the WS listener, will pick it
        // up. The manual "View" button is still there as a last resort.
      }
    }, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [pendingReportId, applyReportUpdate]);

  async function handleGenerate(e: FormEvent) {
    e.preventDefault();
    setGenerating(true);
    setGenerateError(null);
    try {
      const report = await apiClient.generateReport({
        organization_id: organizationId,
        report_period_start: periodStart,
        report_period_end: periodEnd,
      });
      setGenerated(report);
      setSelectedReport(report);
      setPendingReportId(report.status === "final" ? null : report.id);
      await loadReports();
    } catch (err) {
      setGenerateError(err);
    } finally {
      setGenerating(false);
    }
  }

  async function handleViewReport(id: number) {
    setDetailStatus("loading");
    setDetailError(null);
    try {
      const report = await apiClient.getReport(id);
      setSelectedReport(report);
      setDetailStatus("idle");
      setPendingReportId(report.status === "final" ? null : report.id);
    } catch (err) {
      setDetailError(err);
      setDetailStatus("error");
    }
  }

  return (
    <main className="page">
      <h1>Reports</h1>
      <p className="page__intro">
        Generating for <strong>{organizationName}</strong>.
        {isLive && (
          <span className="live-badge" title="Live updates connected">
            <span className="live-badge__dot" aria-hidden="true" /> Live
          </span>
        )}
      </p>

      <section className="card">
        <h2>Generate a report</h2>
        <form className="filter-bar" onSubmit={handleGenerate}>
          <div className="field">
            <label htmlFor="report-start">Period start</label>
            <input
              id="report-start"
              type="date"
              value={periodStart}
              onChange={(e) => setPeriodStart(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="report-end">Period end</label>
            <input
              id="report-end"
              type="date"
              value={periodEnd}
              onChange={(e) => setPeriodEnd(e.target.value)}
              required
            />
          </div>
          <button type="submit" disabled={generating}>
            {generating ? "Generating…" : "Generate report"}
          </button>
        </form>
        {generateError !== null && <ErrorBanner error={generateError} />}
        {generated &&
          (generated.status === "final" ? (
            <p className="selection-confirm">
              Report #{generated.id} generated — {formatKgCo2e(generated.total_emissions_kg_co2e ?? "0")} kg CO2e
              total.
            </p>
          ) : (
            <LoadingState
              label={`Report #${generated.id} is ${STATUS_LABEL[generated.status].toLowerCase()}… it'll appear below automatically once it's ready.`}
            />
          ))}
      </section>

      <section className="card">
        <h2>Past reports</h2>
        {listStatus === "loading" && <LoadingState label="Loading reports…" />}
        {listStatus === "error" && <ErrorBanner error={listError} onRetry={loadReports} />}
        {listStatus === "ready" &&
          (reports.length === 0 ? (
            <p className="empty-state">No reports generated yet.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Period</th>
                  <th scope="col">Generated</th>
                  <th scope="col">Status</th>
                  <th scope="col">Total (kg CO2e)</th>
                  <th scope="col"></th>
                </tr>
              </thead>
              <tbody>
                {reports.map((r) => (
                  <tr key={r.id} className={r.id === selectedReport?.id ? "data-table__row--active" : undefined}>
                    <td>
                      {r.report_period_start} – {r.report_period_end}
                    </td>
                    <td>{formatDateTime(r.generated_at)}</td>
                    <td>
                      <span className={`status-badge status-badge--${r.status}`}>{STATUS_LABEL[r.status]}</span>
                    </td>
                    <td>{r.total_emissions_kg_co2e != null ? formatKgCo2e(r.total_emissions_kg_co2e) : "—"}</td>
                    <td>
                      <button type="button" onClick={() => handleViewReport(r.id)}>
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ))}
      </section>

      {detailStatus === "loading" && <LoadingState label="Loading report…" />}
      {detailStatus === "error" && <ErrorBanner error={detailError} />}
      {selectedReport && detailStatus === "idle" && (
        <section className="card">
          <h2>
            Report #{selectedReport.id} ({selectedReport.report_period_start} – {selectedReport.report_period_end})
          </h2>
          <p>
            <span className={`status-badge status-badge--${selectedReport.status}`}>
              {STATUS_LABEL[selectedReport.status]}
            </span>
          </p>
          {selectedReport.status === "final" && selectedReport.facilities ? (
            <>
              <p className="result-panel__figure">
                {formatKgCo2e(selectedReport.total_emissions_kg_co2e ?? "0")} kg CO2e total
              </p>
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Facility</th>
                    <th scope="col">Emissions (kg CO2e)</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedReport.facilities.map((f) => (
                    <tr key={f.facility_id}>
                      <td>{f.facility_name}</td>
                      <td>{formatKgCo2e(f.total_emissions_kg_co2e)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : (
            <LoadingState
              label={`This report is still ${STATUS_LABEL[selectedReport.status].toLowerCase()} — it'll update automatically once it's ready.`}
            />
          )}
        </section>
      )}
    </main>
  );
}
