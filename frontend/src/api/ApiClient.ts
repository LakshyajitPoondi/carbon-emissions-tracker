/**
 * The single API surface every screen depends on. Components must import
 * `apiClient` from `src/api` and never call `fetch` directly — see
 * mockClient.ts and realClient.ts for the two interchangeable implementations.
 */

import type {
  ConsumptionRecord,
  ConsumptionRecordCreateRequest,
  EmissionFactor,
  EmissionsSummary,
  EmissionSource,
  EmissionSourceCreateRequest,
  Facility,
  FacilityCreateRequest,
  Organization,
  OrganizationCreateRequest,
  Report,
  ReportGenerateRequest,
  ReportSummary,
  SourceType,
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
  createOrganization(req: OrganizationCreateRequest): Promise<Organization>;
  getOrganization(id: number): Promise<Organization>;

  createFacility(req: FacilityCreateRequest): Promise<Facility>;
  listFacilities(organizationId: number): Promise<Facility[]>;

  createEmissionSource(req: EmissionSourceCreateRequest): Promise<EmissionSource>;
  listEmissionSources(facilityId: number): Promise<EmissionSource[]>;

  listEmissionFactors(filters?: EmissionFactorFilters): Promise<EmissionFactor[]>;

  createConsumptionRecord(req: ConsumptionRecordCreateRequest): Promise<ConsumptionRecord>;
  listConsumptionRecords(filters: ConsumptionRecordFilters): Promise<ConsumptionRecord[]>;

  getEmissionsSummary(facilityId: number, filters: EmissionsSummaryFilters): Promise<EmissionsSummary>;

  generateReport(req: ReportGenerateRequest): Promise<Report>;
  getReport(id: number): Promise<Report>;
  listReports(organizationId: number): Promise<ReportSummary[]>;
}
