/** Mirrors docs/api-contract.md — WebSocket section. */

import type { ConsumptionRecord } from "./consumptionRecord";

export interface ConsumptionRecordCreatedMessage {
  type: "consumption_record_created";
  consumption_record: ConsumptionRecord;
}
