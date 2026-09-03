import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "../api";
import type { ConsumptionRecord, Product } from "../types";
import { dateTimeLocalToIso, formatKgCo2e, nowDateTimeLocalValue } from "../utils/format";
import { sourceTypeDisplayLabel } from "../utils/sourceTypePresentation";
import { ErrorBanner } from "./ErrorBanner";

interface Props {
  product: Product;
  facilityId: number;
  onLogged: (record: ConsumptionRecord) => void;
  onBusyChange: (busy: boolean) => void;
}

/** A distinct form: submitting a Product must never submit the source form below. */
export function ProductConsumptionForm({ product, facilityId, onLogged, onBusyChange }: Props) {
  const [quantity, setQuantity] = useState("1");
  const [recordedAt, setRecordedAt] = useState(nowDateTimeLocalValue);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState<ConsumptionRecord | null>(null);
  const [error, setError] = useState<unknown>(null);
  const submissionLocked = useRef(false);
  const configured = Boolean(product.consumption_unit && product.consumption_source_type);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!configured || !product.consumption_unit || submissionLocked.current) return;
    submissionLocked.current = true;
    setSaving(true);
    onBusyChange(true);
    setError(null);
    let created: ConsumptionRecord | null = null;
    try {
      created = await apiClient.createConsumptionRecord({
        product_id: product.id,
        facility_id: facilityId,
        quantity_consumed: quantity,
        unit: product.consumption_unit,
        recorded_at: dateTimeLocalToIso(recordedAt),
      });
      setSaved(created);
      // Keep the lock after success: this match has already been logged.
    } catch (err) {
      submissionLocked.current = false;
      setError(err);
    } finally {
      setSaving(false);
      onBusyChange(false);
    }
    // A list-refresh failure must not turn a successful write into a retry.
    if (created) onLogged(created);
  }

  return (
    <form className="card__col product-consumption-form" onSubmit={handleSubmit} aria-label="Log matched product">
      {!configured ? (
        <p className="empty-state">
          This Product needs a consumption unit and scope before it can be logged. Ask an OWNER or
          ADMIN to configure it in <Link to="/products">Product Library</Link>, then scan it again.
        </p>
      ) : (
        <>
          <p className="result-panel__meta">
            {sourceTypeDisplayLabel(product.consumption_source_type!)} · Uses this Product’s declared
            emissions per {product.consumption_unit}.
          </p>
          <div className="card__row">
            <div className="field">
              <label htmlFor="product-consumption-quantity">Product quantity ({product.consumption_unit})</label>
              <input id="product-consumption-quantity" type="number" min="0.0001" max="9999999999.9999"
                step="0.0001" required value={quantity} disabled={saving || saved !== null}
                onChange={(event) => setQuantity(event.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="product-consumption-date">Product date/time consumed</label>
              <input id="product-consumption-date" type="datetime-local" required value={recordedAt}
                disabled={saving || saved !== null} onChange={(event) => setRecordedAt(event.target.value)} />
            </div>
          </div>
        </>
      )}
      <div className="button-row">
        <button type="submit" disabled={!configured || saving || saved !== null}>
          {saving ? "Logging…" : saved ? "Consumption logged" : "Log consumption"}
        </button>
      </div>
      {error !== null && <ErrorBanner error={error} />}
      {saved && (
        <p className="selection-confirm" role="status">
          Logged {saved.quantity_consumed} {saved.unit} of {saved.product_snapshot?.name ?? product.name}
          {saved.calculation && <> — {formatKgCo2e(saved.calculation.calculated_emissions_kg_co2e, 4)} kg CO2e</>}.
          {" "}<Link to="/dashboard">View Dashboard</Link> (use a date range that includes this entry).
        </p>
      )}
    </form>
  );
}
