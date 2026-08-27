import { useEffect, useRef, useState } from "react";
import { getToken } from "../api/authToken";
import { USE_MOCK_API, WS_BASE_URL } from "../api/config";
import type { ConsumptionRecord, ConsumptionRecordCreatedMessage } from "../types";

function isConsumptionRecordCreatedMessage(data: unknown): data is ConsumptionRecordCreatedMessage {
  return (
    typeof data === "object" &&
    data !== null &&
    (data as { type?: unknown }).type === "consumption_record_created"
  );
}

/**
 * Opens a live WebSocket connection for one facility (per
 * docs/api-contract.md's WebSocket section) and calls onRecordCreated
 * whenever the backend broadcasts a new consumption record for it. Returns
 * whether the connection is currently open, so the screen can show a "Live"
 * indicator.
 *
 * No-op in mock mode — there's no mock WS server, and mock data lives
 * entirely in one browser tab's memory, so there's nothing meaningful to
 * receive "live" from a second connection anyway.
 *
 * Deliberately no reconnection/backoff logic: a single connection attempt
 * per facility-view is treated as sufficient for this project's scope (see
 * the frontend report). A failed or dropped connection just means the
 * screen falls back to its existing non-live behavior — the normal REST
 * fetch (and the manual "View" button) work regardless of whether this
 * socket ever connects.
 */
export function useFacilityLiveUpdates(
  facilityId: number | null,
  onRecordCreated: (record: ConsumptionRecord) => void,
): boolean {
  const [isLive, setIsLive] = useState(false);
  const handlerRef = useRef(onRecordCreated);
  handlerRef.current = onRecordCreated;

  useEffect(() => {
    if (USE_MOCK_API || facilityId == null) {
      setIsLive(false);
      return;
    }

    const token = getToken();
    if (!token) {
      setIsLive(false);
      return;
    }

    const ws = new WebSocket(
      `${WS_BASE_URL}/ws/facilities/${facilityId}?token=${encodeURIComponent(token)}`,
    );

    ws.onopen = () => setIsLive(true);
    ws.onclose = () => setIsLive(false);
    // No explicit handling beyond letting the close event above fire — a
    // connection error and a close are not meaningfully different for this
    // screen's purposes (both just mean "no live updates right now").
    ws.onerror = () => {};

    ws.onmessage = (event: MessageEvent<string>) => {
      let data: unknown;
      try {
        data = JSON.parse(event.data);
      } catch {
        return; // Malformed message — ignore rather than crash the dashboard.
      }
      if (isConsumptionRecordCreatedMessage(data)) {
        handlerRef.current(data.consumption_record);
      }
    };

    return () => {
      ws.close();
      setIsLive(false);
    };
  }, [facilityId]);

  return isLive;
}
