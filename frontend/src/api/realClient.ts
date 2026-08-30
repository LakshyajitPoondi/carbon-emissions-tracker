/** Talks to the real backend over HTTP. Same interface as mockClient.ts. */

import type {
  ApiClient,
  ConsumptionRecordFilters,
  EmissionFactorFilters,
  EmissionsSummaryFilters,
} from "./ApiClient";
import { ApiError } from "./ApiClient";
import { clearToken, getToken } from "./authToken";
import { API_BASE_URL, GRAPHQL_URL } from "./config";
import type { ApiErrorBody, OrganizationOverview } from "../types";

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

/** multipart/form-data POST with the bearer token attached — deliberately no
 * Content-Type header: the browser sets multipart/form-data with the
 * correct boundary itself when the body is a FormData instance, and
 * overriding it manually breaks the boundary. */
function requestMultipart<T>(path: string, formData: FormData): Promise<T> {
  const token = getToken();
  return rawRequest<T>(path, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: formData,
  });
}

/** The one GraphQL query this app makes. Declared as a constant so the shape
 * stays next to the type it fills (see types/organizationOverview.ts).
 *
 * Field names and argument types come from introspecting the live schema:
 * `organization` takes an Int (not a string), and `emissionsSummary`
 * *requires* startDate and endDate — omitting them is a validation error,
 * not a defaulted whole-history summary. */
const ORGANIZATION_OVERVIEW_QUERY = `
  query OrganizationOverview($id: Int!, $startDate: Date!, $endDate: Date!) {
    organization(id: $id) {
      id
      name
      industryType
      facilities {
        id
        name
        location
        emissionsSummary(startDate: $startDate, endDate: $endDate) {
          facilityId
          periodStart
          periodEnd
          totalEmissionsKgCo2e
          bySourceType
        }
      }
    }
  }
`;

/** POST a GraphQL operation, reusing the REST client's auth and 401 handling.
 *
 * Deliberately hand-rolled rather than pulling in Apollo/urql: one query on
 * one page does not justify a client library, a normalized cache, or the
 * bundle that comes with them.
 *
 * Two things GraphQL does differently from REST, both handled here so
 * callers can just try/catch like any other client method:
 *  - it lives at /graphql, outside the /api prefix (hence GRAPHQL_URL);
 *  - a resolver failure comes back as HTTP 200 with an `errors` array, so a
 *    "not found" would otherwise look like success with null data. That is
 *    translated into the same ApiError the REST paths throw, carrying the
 *    resolver's extensions.code (e.g. NOT_FOUND) so ErrorBanner can branch
 *    on code exactly as it does elsewhere.
 */
async function graphqlRequest<T>(query: string, variables: Record<string, unknown>): Promise<T> {
  const token = getToken();

  let res: Response;
  try {
    res = await fetch(GRAPHQL_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ query, variables }),
    });
  } catch {
    throw new ApiError("NETWORK_ERROR", "Could not reach the server. Is the backend running?", 0);
  }

  const body: unknown = await res.json().catch(() => null);

  // Auth is enforced before execution, so a bad token is a transport-level
  // 401 with the standard REST error shape — same handling as rawRequest,
  // including the global event that logs the user out everywhere.
  if (!res.ok) {
    const errorBody = body as ApiErrorBody | null;
    if (res.status === 401) {
      clearToken();
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    throw new ApiError(
      errorBody?.error?.code ?? "GRAPHQL_ERROR",
      errorBody?.error?.message ?? `GraphQL request failed with status ${res.status}`,
      res.status,
    );
  }

  const payload = body as {
    data?: T | null;
    errors?: { message: string; extensions?: { code?: string } }[];
  } | null;

  if (payload?.errors?.length) {
    const first = payload.errors[0];
    throw new ApiError(first.extensions?.code ?? "GRAPHQL_ERROR", first.message, res.status);
  }

  if (payload?.data == null) {
    throw new ApiError("GRAPHQL_ERROR", "The server returned no data for this query.", res.status);
  }

  return payload.data;
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

  // One request, and the server already returns these name-ordered — no
  // client-side sorting, so the picker's order matches the contract rather
  // than a second opinion about it.
  listOrganizations: () => request("/organizations"),

  createFacility: (req) =>
    request("/facilities", { method: "POST", body: JSON.stringify(req) }),

  listFacilities: (organizationId) =>
    request(`/facilities${query({ organization_id: organizationId })}`),

  createEmissionSource: (req) =>
    request("/emission-sources", { method: "POST", body: JSON.stringify(req) }),

  listEmissionSources: (facilityId) =>
    request(`/emission-sources${query({ facility_id: facilityId })}`),

  scanAsset: (facilityId, image) => {
    const formData = new FormData();
    formData.append("image", image, "frame.jpg");
    return requestMultipart(`/facilities/${facilityId}/asset-scan`, formData);
  },

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

  async getOrganizationOverview(organizationId, filters) {
    const data = await graphqlRequest<{ organization: OrganizationOverview | null }>(
      ORGANIZATION_OVERVIEW_QUERY,
      { id: organizationId, startDate: filters.start_date, endDate: filters.end_date },
    );
    if (data.organization === null) {
      // Belt and braces: the resolver raises NOT_FOUND rather than returning
      // null, so this is unreachable today — but a null here would otherwise
      // surface as a blank page instead of an error state.
      throw new ApiError("NOT_FOUND", `Organization ${organizationId} does not exist`, 200);
    }
    return data.organization;
  },

  generateReport: (req) =>
    request("/reports/generate", { method: "POST", body: JSON.stringify(req) }),

  getReport: (id) => request(`/reports/${id}`),

  listReports: (organizationId) => request(`/reports${query({ organization_id: organizationId })}`),
};
