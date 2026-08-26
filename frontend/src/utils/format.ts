/** Formatting helpers for the decimal-string and timestamp fields the contract uses. */

/** Format a contract decimal string (e.g. "708.2000") for display with a fixed precision. */
export function formatKgCo2e(value: string, fractionDigits = 2): string {
  const n = Number(value);
  if (Number.isNaN(n)) return value;
  return n.toLocaleString(undefined, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function formatDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { dateStyle: "medium" });
}

/** YYYY-MM-DD for today, in local time — used as a sensible default for date inputs. */
export function todayInputValue(): string {
  const d = new Date();
  const offsetMs = d.getTimezoneOffset() * 60_000;
  return new Date(d.getTime() - offsetMs).toISOString().slice(0, 10);
}

/** YYYY-MM-DD for N days before today — used as a sensible default period start. */
export function daysAgoInputValue(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  const offsetMs = d.getTimezoneOffset() * 60_000;
  return new Date(d.getTime() - offsetMs).toISOString().slice(0, 10);
}

/** YYYY-MM-DDTHH:mm for now, in local time — default value for a datetime-local input. */
export function nowDateTimeLocalValue(): string {
  const d = new Date();
  const offsetMs = d.getTimezoneOffset() * 60_000;
  return new Date(d.getTime() - offsetMs).toISOString().slice(0, 16);
}

/** Convert a <input type="datetime-local"> value (local time, no timezone) to a UTC ISO string. */
export function dateTimeLocalToIso(value: string): string {
  return new Date(value).toISOString();
}
