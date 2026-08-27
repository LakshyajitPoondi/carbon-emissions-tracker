import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "../api";
import { AssetScanCapture } from "../components/AssetScanCapture";
import { ErrorBanner } from "../components/ErrorBanner";
import { LoadingState } from "../components/LoadingState";
import { useAppState } from "../context/AppStateContext";
import type { ConsumptionRecord, EmissionSource } from "../types";
import { dateTimeLocalToIso, formatDateTime, formatKgCo2e, nowDateTimeLocalValue } from "../utils/format";

type ListStatus = "loading" | "ready" | "error";

export function ConsumptionPage() {
  const { facility } = useAppState();

  if (!facility) {
    return (
      <main className="page">
        <h1>Log Consumption</h1>
        <p className="empty-state">
          Select a facility on the <Link to="/">Setup</Link> screen first.
        </p>
      </main>
    );
  }

  return <ConsumptionForFacility facilityId={facility.id} facilityName={facility.name} />;
}

function ConsumptionForFacility({ facilityId, facilityName }: { facilityId: number; facilityName: string }) {
  const [sources, setSources] = useState<EmissionSource[]>([]);
  const [sourcesStatus, setSourcesStatus] = useState<ListStatus>("loading");
  const [sourcesError, setSourcesError] = useState<unknown>(null);

  const [records, setRecords] = useState<ConsumptionRecord[]>([]);
  const [recordsStatus, setRecordsStatus] = useState<ListStatus>("loading");
  const [recordsError, setRecordsError] = useState<unknown>(null);

  const [emissionSourceId, setEmissionSourceId] = useState<number | "">("");
  const [quantity, setQuantity] = useState("");
  const [recordedAt, setRecordedAt] = useState(nowDateTimeLocalValue());
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<unknown>(null);
  const [lastCreated, setLastCreated] = useState<ConsumptionRecord | null>(null);

  const loadSources = useCallback(async () => {
    setSourcesStatus("loading");
    setSourcesError(null);
    try {
      const data = await apiClient.listEmissionSources(facilityId);
      setSources(data);
      setSourcesStatus("ready");
      setEmissionSourceId((current) => (current === "" && data.length > 0 ? data[0].id : current));
    } catch (err) {
      setSourcesError(err);
      setSourcesStatus("error");
    }
  }, [facilityId]);

  const loadRecords = useCallback(async () => {
    setRecordsStatus("loading");
    setRecordsError(null);
    try {
      const data = await apiClient.listConsumptionRecords({ facility_id: facilityId });
      setRecords(data);
      setRecordsStatus("ready");
    } catch (err) {
      setRecordsError(err);
      setRecordsStatus("error");
    }
  }, [facilityId]);

  useEffect(() => {
    loadSources();
    loadRecords();
  }, [loadSources, loadRecords]);

  const selectedSource = sources.find((s) => s.id === emissionSourceId);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (emissionSourceId === "" || !selectedSource) return;
    setSubmitting(true);
    setSubmitError(null);
    setLastCreated(null);
    try {
      const record = await apiClient.createConsumptionRecord({
        emission_source_id: selectedSource.id,
        facility_id: facilityId,
        quantity_consumed: quantity,
        unit: selectedSource.unit_of_measurement,
        recorded_at: dateTimeLocalToIso(recordedAt),
      });
      setLastCreated(record);
      setQuantity("");
      await loadRecords();
    } catch (err) {
      setSubmitError(err);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page">
      <h1>Log Consumption</h1>
      <p className="page__intro">
        Recording for <strong>{facilityName}</strong>. Emissions are calculated automatically the moment
        you submit — no separate calculate step.
      </p>

      <section className="card">
        {sourcesStatus === "loading" && <LoadingState label="Loading emission sources…" />}
        {sourcesStatus === "error" && <ErrorBanner error={sourcesError} onRetry={loadSources} />}
        {sourcesStatus === "ready" && sources.length === 0 && (
          <p className="empty-state">
            This facility has no emission sources yet. Add one on the <Link to="/">Setup</Link> screen.
          </p>
        )}
        {sourcesStatus === "ready" && sources.length > 0 && (
          <AssetScanCapture
            facilityId={facilityId}
            onMatched={(source) => setEmissionSourceId(source.id)}
          />
        )}

        {sourcesStatus === "ready" && sources.length > 0 && (
          <form onSubmit={handleSubmit} className="card__col">
            <div className="field">
              <label htmlFor="consumption-source">Emission source</label>
              <select
                id="consumption-source"
                value={emissionSourceId}
                onChange={(e) => setEmissionSourceId(Number(e.target.value))}
              >
                {sources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.source_name} ({s.source_type})
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="consumption-quantity">
                Quantity consumed{selectedSource ? ` (${selectedSource.unit_of_measurement})` : ""}
              </label>
              <input
                id="consumption-quantity"
                type="number"
                step="any"
                min="0"
                required
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                placeholder="1250.5"
              />
            </div>
            <div className="field">
              <label htmlFor="consumption-recorded-at">Date/time consumed</label>
              <input
                id="consumption-recorded-at"
                type="datetime-local"
                required
                value={recordedAt}
                onChange={(e) => setRecordedAt(e.target.value)}
              />
            </div>
            <button type="submit" disabled={submitting}>
              {submitting ? "Calculating…" : "Log consumption"}
            </button>
            {submitError !== null && <ErrorBanner error={submitError} />}
          </form>
        )}

        {lastCreated?.calculation && (
          <div className="result-panel" role="status">
            <h3>Emissions calculated</h3>
            <p className="result-panel__figure">
              {formatKgCo2e(lastCreated.calculation.calculated_emissions_kg_co2e, 4)} kg CO2e
            </p>
            <p className="result-panel__meta">
              Factor #{lastCreated.calculation.emission_factor_id} · calculated{" "}
              {lastCreated.calculation.calculation_date}
            </p>
          </div>
        )}
      </section>

      <section className="card">
        <h2>Recent records</h2>
        {recordsStatus === "loading" && <LoadingState label="Loading consumption records…" />}
        {recordsStatus === "error" && <ErrorBanner error={recordsError} onRetry={loadRecords} />}
        {recordsStatus === "ready" &&
          (records.length === 0 ? (
            <p className="empty-state">No consumption records logged yet.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Recorded at</th>
                  <th scope="col">Source</th>
                  <th scope="col">Quantity</th>
                  <th scope="col">Emissions (kg CO2e)</th>
                </tr>
              </thead>
              <tbody>
                {records.map((r) => {
                  const source = sources.find((s) => s.id === r.emission_source_id);
                  return (
                    <tr key={r.id}>
                      <td>{formatDateTime(r.recorded_at)}</td>
                      <td>{source ? source.source_name : `Source #${r.emission_source_id}`}</td>
                      <td>
                        {r.quantity_consumed} {r.unit}
                      </td>
                      <td>
                        {r.calculation ? formatKgCo2e(r.calculation.calculated_emissions_kg_co2e, 4) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ))}
      </section>
    </main>
  );
}
