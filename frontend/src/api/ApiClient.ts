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
  EmissionSourceUpdateRequest,
  Facility,
  FacilityCreateRequest,
  LoginRequest,
  Organization,
  OrganizationCreateRequest,
  OrganizationMember,
  JoinCode,
  JoinRequest,
  JoinRequestApprovalRequest,
  JoinRequestCreateRequest,
  MemberRoleUpdateRequest,
  OrganizationOverview,
  Product,
  ProductCreateRequest,
  ProductUpdateRequest,
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

  getOrganizationJoinCode(organizationId: number): Promise<JoinCode>;
  regenerateOrganizationJoinCode(organizationId: number): Promise<JoinCode>;
  submitJoinRequest(req: JoinRequestCreateRequest): Promise<JoinRequest>;
  listMyPendingJoinRequests(): Promise<JoinRequest[]>;
  listPendingJoinRequests(organizationId: number): Promise<JoinRequest[]>;
  approveJoinRequest(
    organizationId: number,
    requestId: number,
    req: JoinRequestApprovalRequest,
  ): Promise<JoinRequest>;
  rejectJoinRequest(organizationId: number, requestId: number): Promise<JoinRequest>;
  listOrganizationMembers(organizationId: number): Promise<OrganizationMember[]>;
  updateOrganizationMemberRole(
    organizationId: number,
    userId: number,
    req: MemberRoleUpdateRequest,
  ): Promise<OrganizationMember>;
  removeOrganizationMember(organizationId: number, userId: number): Promise<void>;

  createFacility(req: FacilityCreateRequest): Promise<Facility>;
  listFacilities(organizationId: number): Promise<Facility[]>;

  createEmissionSource(req: EmissionSourceCreateRequest): Promise<EmissionSource>;
  updateEmissionSource(id: number, req: EmissionSourceUpdateRequest): Promise<EmissionSource>;
  listEmissionSources(facilityId: number): Promise<EmissionSource[]>;

  createProduct(req: ProductCreateRequest): Promise<Product>;
  listProducts(organizationId: number): Promise<Product[]>;
  getProduct(id: number): Promise<Product>;
  updateProduct(id: number, req: ProductUpdateRequest): Promise<Product>;
  deleteProduct(id: number): Promise<void>;

  /** image is a captured webcam frame (canvas.toBlob output). */
  scanAsset(facilityId: number, image: Blob): Promise<AssetScanResult>;

  listEmissionFactors(filters?: EmissionFactorFilters): Promise<EmissionFactor[]>;

  createConsumptionRecord(req: ConsumptionRecordCreateRequest): Promise<ConsumptionRecord>;
  listConsumptionRecords(filters: ConsumptionRecordFilters): Promise<ConsumptionRecord[]>;

  getEmissionsSummary(facilityId: number, filters: EmissionsSummaryFilters): Promise<EmissionsSummary>;

  /**
   * One organization with every facility and each facility's emissions
   * summary, in a single round trip, via the read-only GraphQL query.
   *
   * This is the same data the REST endpoints expose — the backend resolves
   * `emissionsSummary` through the identical service function that
   * `GET /facilities/{id}/emissions-summary` uses, so the numbers agree by
   * construction. The difference is the trip count: REST needs
   * 1 + 1 + N calls (organization, facilities, then a summary per facility),
   * this needs one.
   */
  getOrganizationOverview(
    organizationId: number,
    filters: EmissionsSummaryFilters,
  ): Promise<OrganizationOverview>;

  generateReport(req: ReportGenerateRequest): Promise<Report>;
  getReport(id: number): Promise<Report>;
  listReports(organizationId: number): Promise<ReportSummary[]>;
}
