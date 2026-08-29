/**
 * The single API surface every screen depends on. Components must import
 * `apiClient` from `src/api` and never call `fetch` directly — see
 * mockClient.ts and realClient.ts for the two interchangeable implementations.
 */

import type {
  AssetScanResult,
  ConsumptionRecord,
  ConsumptionRecordCreateRequest,
  EmissionFactor,
  EmissionsSummary,
  EmissionSource,
  EmissionSourceCreateRequest,
  Facility,
  FacilityCreateRequest,
  LoginRequest,
  Organization,
  OrganizationCreateRequest,
  RegisterRequest,
  Report,
  ReportGenerateRequest,
  ReportSummary,
  SourceType,
  TokenResponse,
  User,
} from "../types";

/** Thrown by both clients on any non-2xx response, carrying the contract's error.code. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

export interface EmissionFactorFilters {
  source_type?: SourceType;
  region?: string;
}

export interface ConsumptionRecordFilters {
  facility_id: number;
  start_date?: string;
  end_date?: string;
}

export interface EmissionsSummaryFilters {
  start_date: string;
  end_date: string;
}

export interface ApiClient {
  register(req: RegisterRequest): Promise<User>;
  login(req: LoginRequest): Promise<TokenResponse>;

  createOrganization(req: OrganizationCreateRequest): Promise<Organization>;
  getOrganization(id: number): Promise<Organization>;

  /**
   * GET /organizations — the organizations the current user is a member of,
   * name-ordered by the server, `[]` when they belong to none.
   *
   * The server is the source of truth for discovery: no client-side cache of
   * organization ids is involved, so a user sees their organizations on any
   * browser, including one with empty storage.
   */
  listOrganizations(): Promise<Organization[]>;

  createFacility(req: FacilityCreateRequest): Promise<Facility>;
  listFacilities(organizationId: number): Promise<Facility[]>;

  createEmissionSource(req: EmissionSourceCreateRequest): Promise<EmissionSource>;
  listEmissionSources(facilityId: number): Promise<EmissionSource[]>;

  /** image is a captured webcam frame (canvas.toBlob output). */
  scanAsset(facilityId: number, image: Blob): Promise<AssetScanResult>;

  listEmissionFactors(filters?: EmissionFactorFilters): Promise<EmissionFactor[]>;

  createConsumptionRecord(req: ConsumptionRecordCreateRequest): Promise<ConsumptionRecord>;
  listConsumptionRecords(filters: ConsumptionRecordFilters): Promise<ConsumptionRecord[]>;

  getEmissionsSummary(facilityId: number, filters: EmissionsSummaryFilters): Promise<EmissionsSummary>;

  generateReport(req: ReportGenerateRequest): Promise<Report>;
  getReport(id: number): Promise<Report>;
  listReports(organizationId: number): Promise<ReportSummary[]>;
}
