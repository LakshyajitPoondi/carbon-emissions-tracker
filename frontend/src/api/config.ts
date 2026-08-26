/**
 * The one switch point between the mock client and the real backend.
 * Set VITE_USE_MOCK_API=false (in frontend/.env.local) to talk to the real
 * API — do not scatter this check anywhere else in the app.
 */
export const USE_MOCK_API: boolean = import.meta.env.VITE_USE_MOCK_API !== "false";

export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";
