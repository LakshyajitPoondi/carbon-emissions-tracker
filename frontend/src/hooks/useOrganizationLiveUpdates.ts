import { useEffect, useRef, useState } from "react";
import { getToken } from "../api/authToken";
import { USE_MOCK_API, WS_BASE_URL } from "../api/config";
import type { Report, ReportGeneratedMessage } from "../types";

function isReportGeneratedMessage(data: unknown): data is ReportGeneratedMessage {
  return (
    typeof data === "object" && data !== null && (data as { type?: unknown }).type === "report_generated"
  );
}

/**
 * Opens a live WebSocket connection for one organization (per
 * docs/api-contract.md's WebSocket section) and calls onReportGenerated
 * whenever the backend broadcasts that an async report-generation task has
 * reached "final". Returns whether the connection is currently open, so the
 * screen can show a "Live" indicator.
 *
 * Deliberately the same shape as useFacilityLiveUpdates.ts, adapted for the
 * organization channel: no-op in mock mode (there's no mock WS server, and
 * the mock's generateReport already resolves synchronously to "final", so
 * there's nothing to push here anyway), and no reconnection/backoff logic —
 * a single connection attempt per organization-view is treated as
 * sufficient for this project's scope.
 *
 * Unlike the facility channel, a dropped or never-established connection
 * here isn't just a missed "nice to have" — a report the user is waiting
 * on could otherwise never visibly finish. ReportsPage.tsx accounts for
 * that by pairing this hook with a periodic GET /reports/{id} poll as a
 * backup for as long as a report is pending/processing, so the UI doesn't
 * depend on this socket firing.
 */
export function useOrganizationLiveUpdates(
  organizationId: number | null,
  onReportGenerated: (report: Report) => void,
): boolean {
  const [isLive, setIsLive] = useState(false);
  const handlerRef = useRef(onReportGenerated);
  handlerRef.current = onReportGenerated;

  useEffect(() => {
    if (USE_MOCK_API || organizationId == null) {
      setIsLive(false);
      return;
    }

    const token = getToken();
    if (!token) {
      setIsLive(false);
      return;
    }

    const ws = new WebSocket(
      `${WS_BASE_URL}/ws/organizations/${organizationId}?token=${encodeURIComponent(token)}`,
    );

    ws.onopen = () => setIsLive(true);
    ws.onclose = () => setIsLive(false);
    // Same reasoning as useFacilityLiveUpdates: a connection error and a
    // close aren't meaningfully different here — either way the polling
    // fallback in ReportsPage.tsx is what actually guarantees progress.
    ws.onerror = () => {};

    ws.onmessage = (event: MessageEvent<string>) => {
      let data: unknown;
      try {
        data = JSON.parse(event.data);
      } catch {
        return; // Malformed message — ignore rather than crash the screen.
      }
      if (isReportGeneratedMessage(data)) {
        handlerRef.current(data.report);
      }
    };

    return () => {
      ws.close();
      setIsLive(false);
    };
  }, [organizationId]);

  return isLive;
}
