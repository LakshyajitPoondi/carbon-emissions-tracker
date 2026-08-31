import type { FormEventHandler } from "react";

interface DateRangeFilterProps {
  idPrefix: string;
  startDate: string;
  endDate: string;
  onStartDateChange: (value: string) => void;
  onEndDateChange: (value: string) => void;
  onSubmit: FormEventHandler<HTMLFormElement>;
  loading: boolean;
}

/** Shared date-range controls for the Dashboard and Organization Overview. */
export function DateRangeFilter({
  idPrefix,
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
  onSubmit,
  loading,
}: DateRangeFilterProps) {
  const startId = `${idPrefix}-start`;
  const endId = `${idPrefix}-end`;

  return (
    <form className="filter-bar date-range-filter" onSubmit={onSubmit}>
      <div className="field">
        <label htmlFor={startId}>Start date</label>
        <input
          id={startId}
          type="date"
          value={startDate}
          onChange={(event) => onStartDateChange(event.target.value)}
          required
        />
      </div>
      <div className="field">
        <label htmlFor={endId}>End date</label>
        <input
          id={endId}
          type="date"
          value={endDate}
          onChange={(event) => onEndDateChange(event.target.value)}
          required
        />
      </div>
      <button className="date-range-filter__submit" type="submit" disabled={loading}>
        {loading ? "Loading…" : "View"}
      </button>
    </form>
  );
}
