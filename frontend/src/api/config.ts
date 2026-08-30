/**
 * The one switch point between the mock client and the real backend.
 * Set VITE_USE_MOCK_API=false (in frontend/.env.local) to talk to the real
 * API — do not scatter this check anywhere else in the app.
 */
export const USE_MOCK_API: boolean = import.meta.env.VITE_USE_MOCK_API !== "false";

export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

/** WebSocket endpoints (see docs/api-contract.md's WebSocket section) sit at
 * the root, not under /api — derived from API_BASE_URL rather than a
 * separate env var so the two never drift apart. */
export const WS_BASE_URL: string = API_BASE_URL.replace(/^http/, "ws").replace(/\/api\/?$/, "");

/** GraphQL sits at the root too, not under /api — same reasoning and same
 * derivation as WS_BASE_URL, so one env var still configures everything. */
export const GRAPHQL_URL: string = `${API_BASE_URL.replace(/\/api\/?$/, "")}/graphql`;
