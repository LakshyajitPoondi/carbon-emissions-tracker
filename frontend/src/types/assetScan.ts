/** Mirrors docs/api-contract.md — Asset Scan section. */

import type { EmissionSource } from "./emissionSource";
import type { Product } from "./product";

export type AssetScanResult =
  | { match_type: "emission_source"; data: EmissionSource }
  | { match_type: "product"; data: Product };
