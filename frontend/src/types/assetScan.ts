/** Mirrors docs/api-contract.md — Asset Scan section. */

import type { EmissionSource } from "./emissionSource";

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface AssetScanResult {
  decoded_value: string;
  bounding_box: BoundingBox;
  emission_source: EmissionSource;
}
