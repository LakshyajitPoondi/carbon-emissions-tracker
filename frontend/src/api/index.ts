import type { ApiClient } from "./ApiClient";
import { USE_MOCK_API } from "./config";
import { mockClient } from "./mockClient";
import { realClient } from "./realClient";

/** The only client components should ever import. */
export const apiClient: ApiClient = USE_MOCK_API ? mockClient : realClient;

export { ApiError } from "./ApiClient";
export type {
  ApiClient,
  ConsumptionRecordFilters,
  EmissionFactorFilters,
  EmissionsSummaryFilters,
} from "./ApiClient";
export { USE_MOCK_API } from "./config";
