import type { SourceType } from "../types";

type GhgScope = "Scope 1" | "Scope 2" | "Scope 3";

interface SourceTypePresentation {
  scope: GhgScope;
  activity: string;
  displayLabel: string;
}

/**
 * Presentation-only mapping from the frozen API's source categories to the
 * GHG Protocol terminology used in the UI. API requests and responses keep
 * using ENERGY / FUEL / RESOURCE unchanged.
 */
export const SOURCE_TYPE_PRESENTATION = {
  FUEL: {
    scope: "Scope 1",
    activity: "Stationary Combustion",
    displayLabel: "Scope 1 — Stationary Combustion",
  },
  ENERGY: {
    scope: "Scope 2",
    activity: "Purchased Energy",
    displayLabel: "Scope 2 — Purchased Energy",
  },
  RESOURCE: {
    scope: "Scope 3",
    activity: "Purchased Goods",
    displayLabel: "Scope 3 — Purchased Goods",
  },
} satisfies Record<SourceType, SourceTypePresentation>;

/** Display order follows the GHG Protocol scope sequence, not the API enum order. */
export const GHG_SCOPE_SOURCE_TYPES = ["FUEL", "ENERGY", "RESOURCE"] as const satisfies readonly SourceType[];

export function sourceTypeDisplayLabel(sourceType: SourceType): string {
  return SOURCE_TYPE_PRESENTATION[sourceType].displayLabel;
}

const coverageDescriptions = GHG_SCOPE_SOURCE_TYPES.map((sourceType) => {
  const { scope, activity } = SOURCE_TYPE_PRESENTATION[sourceType];
  return `${scope} (${activity.toLowerCase()})`;
});

export const GHG_SCOPE_TOTAL_CAPTION =
  `Total includes ${coverageDescriptions.slice(0, -1).join(", ")}, and ${coverageDescriptions.at(-1)} emissions.`;
