import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "../api";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { useAppState } from "../context/AppStateContext";
import type { Report, ReportSummary } from "../types";
import { daysAgoInputValue, formatDateTime, formatKgCo2e, todayInputValue } from "../utils/format";

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
        {generated && (
          <p className="selection-confirm">
            Report #{generated.id} generated — {formatKgCo2e(generated.total_emissions_kg_co2e)} kg CO2e total.
          </p>
        )}
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
                    <td>{r.status}</td>
                    <td>{formatKgCo2e(r.total_emissions_kg_co2e)}</td>
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
          <p className="result-panel__figure">
            {formatKgCo2e(selectedReport.total_emissions_kg_co2e)} kg CO2e total
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
        </section>
      )}
    </main>
  );
}
