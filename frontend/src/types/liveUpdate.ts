/** Mirrors docs/api-contract.md — WebSocket section. */

import type { ConsumptionRecord } from "./consumptionRecord";
import type { Report } from "./report";

export interface ConsumptionRecordCreatedMessage {
  type: "consumption_record_created";
  consumption_record: ConsumptionRecord;
}

/** Pushed on the GET /ws/organizations/{organization_id} channel when an
 * async report-generation task reaches "final". Same shape as the
 * GET /reports/{id} response, sent in full. */
export interface ReportGeneratedMessage {
  type: "report_generated";
  report: Report;
}
