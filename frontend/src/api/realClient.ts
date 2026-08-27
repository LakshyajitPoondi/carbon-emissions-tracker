/** Talks to the real backend over HTTP. Same interface as mockClient.ts. */

import type {
  ApiClient,
  ConsumptionRecordFilters,
  EmissionFactorFilters,
  EmissionsSummaryFilters,
} from "./ApiClient";
import { ApiError } from "./ApiClient";
import { clearToken, getToken } from "./authToken";
import { API_BASE_URL } from "./config";
import type { ApiErrorBody } from "../types";

/** Fired whenever a request comes back 401 — AuthContext listens for this to
 * clear its state and send the user back to /login, from anywhere in the app. */
export const UNAUTHORIZED_EVENT = "auth:unauthorized";

function query(params: Record<string, string | number | undefined>): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) usp.set(key, String(value));
  }
  const s = usp.toString();
  return s ? `?${s}` : "";
}

/** Lowest-level fetch wrapper: no assumptions about request Content-Type, so
 * both JSON requests and the form-encoded login request can share it. */
async function rawRequest<T>(path: string, init: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new ApiError("NETWORK_ERROR", "Could not reach the server. Is the backend running?", 0);
  }

  const body: unknown = await res.json().catch(() => null);

  if (!res.ok) {
    const errorBody = body as ApiErrorBody | null;
    if (res.status === 401) {
      clearToken();
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    throw new ApiError(
      errorBody?.error?.code ?? "UNKNOWN_ERROR",
      errorBody?.error?.message ?? `Request failed with status ${res.status}`,
      res.status,
    );
  }

  return body as T;
}

/** JSON request with the bearer token attached, for every non-auth endpoint. */
function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  return rawRequest<T>(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
}

export const realClient: ApiClient = {
  register: (req) => request("/auth/register", { method: "POST", body: JSON.stringify(req) }),

  login: (req) => {
    // POST /auth/token is OAuth2's password flow — form-encoded, not JSON,
    // and unauthenticated, so it goes through rawRequest directly.
    const params = new URLSearchParams();
    params.set("username", req.email);
    params.set("password", req.password);
    return rawRequest("/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: params.toString(),
    });
  },

  createOrganization: (req) =>
    request("/organizations", { method: "POST", body: JSON.stringify(req) }),

  getOrganization: (id) => request(`/organizations/${id}`),

  createFacility: (req) =>
    request("/facilities", { method: "POST", body: JSON.stringify(req) }),

  listFacilities: (organizationId) =>
    request(`/facilities${query({ organization_id: organizationId })}`),

  createEmissionSource: (req) =>
    request("/emission-sources", { method: "POST", body: JSON.stringify(req) }),

  listEmissionSources: (facilityId) =>
    request(`/emission-sources${query({ facility_id: facilityId })}`),

  listEmissionFactors: (filters?: EmissionFactorFilters) =>
    request(`/emission-factors${query({ source_type: filters?.source_type, region: filters?.region })}`),

  createConsumptionRecord: (req) =>
    request("/consumption-records", { method: "POST", body: JSON.stringify(req) }),

  listConsumptionRecords: (filters: ConsumptionRecordFilters) =>
    request(
      `/consumption-records${query({
        facility_id: filters.facility_id,
        start_date: filters.start_date,
        end_date: filters.end_date,
      })}`,
    ),

  getEmissionsSummary: (facilityId, filters: EmissionsSummaryFilters) =>
    request(
      `/facilities/${facilityId}/emissions-summary${query({
        start_date: filters.start_date,
        end_date: filters.end_date,
      })}`,
    ),

  generateReport: (req) =>
    request("/reports/generate", { method: "POST", body: JSON.stringify(req) }),

  getReport: (id) => request(`/reports/${id}`),

  listReports: (organizationId) => request(`/reports${query({ organization_id: organizationId })}`),
};
