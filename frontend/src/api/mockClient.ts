/**
 * In-memory mock backend. Implements the exact same ApiClient interface as
 * realClient.ts, returns data shaped exactly like docs/api-contract.md, and
 * replicates the backend's validation/error behavior (404s, 422s, and
 * NO_MATCHING_FACTOR) so every screen can be built and demoed without the
 * real API running.
 *
 * Seed data mirrors backend/app/seed.py's emission factors so the numbers
 * behave the same way a real integration would.
 *
 * Note on arithmetic: the real backend uses exact Decimal math (see
 * backend/app/services/emissions.py). This mock uses plain floating-point
 * with toFixed() — adequate for demo realism, not for financial precision.
 */

import type {
  ApiClient,
  ConsumptionRecordFilters,
  EmissionFactorFilters,
  EmissionsSummaryFilters,
} from "./ApiClient";
import { ApiError } from "./ApiClient";
import type {
  AssetScanResult,
  ConsumptionRecord,
  ConsumptionRecordCreateRequest,
  EmissionCalculation,
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
  User,
} from "../types";
import { SOURCE_TYPES } from "../types";

const LATENCY_MS = 350;
const DEFAULT_REGION = "IN";

function delay(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, LATENCY_MS));
}

function nowIso(): string {
  return new Date().toISOString();
}

function todayDate(): string {
  return nowIso().slice(0, 10);
}

function notEmpty(value: string | undefined | null): boolean {
  return typeof value === "string" && value.trim().length > 0;
}

// ---------------------------------------------------------------------------
// In-memory store, pre-seeded so every screen has realistic data on first load.
// ---------------------------------------------------------------------------

const nextId = {
  organization: 2,
  facility: 2,
  emissionSource: 4,
  consumptionRecord: 1,
  calculation: 1,
  report: 1,
};

const organizations: Organization[] = [
  { id: 1, name: "Acme Manufacturing", industry_type: "manufacturing", created_at: "2026-08-01T09:00:00Z" },
];

const facilities: Facility[] = [
  {
    id: 1,
    organization_id: 1,
    name: "Chennai Plant",
    location: "Chennai, TN",
    facility_type: "factory",
    created_at: "2026-08-01T09:05:00Z",
    updated_at: "2026-08-01T09:05:00Z",
  },
];

const emissionSources: EmissionSource[] = [
  {
    id: 1,
    facility_id: 1,
    source_type: "ENERGY",
    source_name: "Grid electricity",
    unit_of_measurement: "kWh",
    // The only seeded source with a barcode — see scanAsset below for why.
    barcode_value: "ENSRC-DEMO-001",
    created_at: "2026-08-01T09:10:00Z",
    updated_at: "2026-08-01T09:10:00Z",
  },
  {
    id: 2,
    facility_id: 1,
    source_type: "FUEL",
    source_name: "Diesel generator",
    unit_of_measurement: "litre",
    barcode_value: null,
    created_at: "2026-08-01T09:11:00Z",
    updated_at: "2026-08-01T09:11:00Z",
  },
  {
    id: 3,
    facility_id: 1,
    source_type: "RESOURCE",
    source_name: "Portland cement",
    unit_of_measurement: "kg",
    barcode_value: null,
    created_at: "2026-08-01T09:12:00Z",
    updated_at: "2026-08-01T09:12:00Z",
  },
];

// Mirrors backend/app/seed.py exactly.
const emissionFactors: EmissionFactor[] = [
  {
    id: 1,
    source_type: "ENERGY",
    region: "IN",
    factor_value: "0.708200",
    unit: "kg_co2e_per_kwh",
    valid_from: "2026-01-01",
    valid_to: null,
    source_reference:
      "CEA (Central Electricity Authority) CO2 Baseline Database for the Indian Power Sector, " +
      "Version 19, December 2023 — weighted average grid emission factor for India",
  },
  {
    id: 2,
    source_type: "FUEL",
    region: "IN",
    factor_value: "2.683000",
    unit: "kg_co2e_per_litre",
    valid_from: "2026-01-01",
    valid_to: null,
    source_reference:
      "IPCC 2006 Guidelines for National Greenhouse Gas Inventories, Volume 2, Chapter 3, " +
      "Table 3.3.1 — diesel oil (gas/diesel oil) default emission factor",
  },
  {
    id: 3,
    source_type: "RESOURCE",
    region: "IN",
    factor_value: "0.910000",
    unit: "kg_co2e_per_kg",
    valid_from: "2026-01-01",
    valid_to: null,
    source_reference:
      "GHG Protocol — Emission Factors for Cross Sector Tools, Scope 3: purchased goods — " +
      "Portland cement, India average",
  },
];

const consumptionRecords: ConsumptionRecord[] = [];
const reports: Report[] = [];

// Preseeded so the login screen is usable standalone in mock mode.
interface MockUser {
  id: number;
  email: string;
  password: string;
  created_at: string;
}
const users: MockUser[] = [
  { id: 1, email: "demo@example.com", password: "demopassword123", created_at: "2026-08-01T08:00:00Z" },
];
let nextUserId = 2;

function seedConsumptionRecord(
  emissionSourceId: number,
  quantity: string,
  recordedAt: string,
): void {
  const source = emissionSources.find((s) => s.id === emissionSourceId);
  if (!source) return;
  const factor = findApplicableFactor(source.source_type, recordedAt.slice(0, 10));
  const calculation: EmissionCalculation | null = factor
    ? {
        id: nextId.calculation++,
        emission_factor_id: factor.id,
        calculated_emissions_kg_co2e: multiply(quantity, factor.factor_value),
        calculation_date: recordedAt.slice(0, 10),
      }
    : null;
  consumptionRecords.push({
    id: nextId.consumptionRecord++,
    emission_source_id: emissionSourceId,
    facility_id: source.facility_id,
    quantity_consumed: quantity,
    unit: source.unit_of_measurement,
    recorded_at: recordedAt,
    created_at: recordedAt,
    calculation,
  });
}

// ---------------------------------------------------------------------------
// Lookup helpers — mirror the backend's 404/422 rules exactly.
// ---------------------------------------------------------------------------

function requireOrganization(id: number): Organization {
  const org = organizations.find((o) => o.id === id);
  if (!org) throw new ApiError("NOT_FOUND", `Organization ${id} does not exist`, 404);
  return org;
}

function requireFacility(id: number): Facility {
  const facility = facilities.find((f) => f.id === id);
  if (!facility) throw new ApiError("NOT_FOUND", `Facility ${id} does not exist`, 404);
  return facility;
}

function requireEmissionSource(id: number): EmissionSource {
  const source = emissionSources.find((s) => s.id === id);
  if (!source) throw new ApiError("NOT_FOUND", `Emission source ${id} does not exist`, 404);
  return source;
}

function findApplicableFactor(sourceType: SourceType, asOfDate: string): EmissionFactor | undefined {
  return emissionFactors
    .filter(
      (f) =>
        f.source_type === sourceType &&
        f.region === DEFAULT_REGION &&
        f.valid_from <= asOfDate &&
        (f.valid_to === null || f.valid_to >= asOfDate),
    )
    .sort((a, b) => (a.valid_from < b.valid_from ? 1 : -1))[0];
}

function multiply(a: string, b: string): string {
  return (parseFloat(a) * parseFloat(b)).toFixed(4);
}

function sumBySourceType(facilityId: number, start: string, end: string): Record<SourceType, string> {
  const totals: Record<SourceType, number> = { ENERGY: 0, FUEL: 0, RESOURCE: 0 };
  for (const record of consumptionRecords) {
    if (record.facility_id !== facilityId || !record.calculation) continue;
    const recordDate = record.recorded_at.slice(0, 10);
    if (recordDate < start || recordDate > end) continue;
    const source = emissionSources.find((s) => s.id === record.emission_source_id);
    if (!source) continue;
    totals[source.source_type] += parseFloat(record.calculation.calculated_emissions_kg_co2e);
  }
  return {
    ENERGY: totals.ENERGY.toFixed(2),
    FUEL: totals.FUEL.toFixed(2),
    RESOURCE: totals.RESOURCE.toFixed(2),
  };
}

function facilityTotal(facilityId: number, start: string, end: string): string {
  const bySourceType = sumBySourceType(facilityId, start, end);
  const total = SOURCE_TYPES.reduce((sum, type) => sum + parseFloat(bySourceType[type]), 0);
  return total.toFixed(2);
}

function reportBreakdown(organizationId: number, start: string, end: string) {
  const orgFacilities = facilities.filter((f) => f.organization_id === organizationId);
  const facilityBreakdown = orgFacilities.map((f) => ({
    facility_id: f.id,
    facility_name: f.name,
    total_emissions_kg_co2e: facilityTotal(f.id, start, end),
  }));
  const total = facilityBreakdown
    .reduce((sum, f) => sum + parseFloat(f.total_emissions_kg_co2e), 0)
    .toFixed(2);
  return { total, facilityBreakdown };
}

function toSummary(report: Report): ReportSummary {
  return {
    id: report.id,
    organization_id: report.organization_id,
    report_period_start: report.report_period_start,
    report_period_end: report.report_period_end,
    generated_at: report.generated_at,
    status: report.status,
    total_emissions_kg_co2e: report.total_emissions_kg_co2e,
  };
}

// A few pre-seeded consumption records so the Dashboard/Reports screens have
// non-trivial data before the user has entered anything.
seedConsumptionRecord(1, "1200.5000", "2026-08-05T08:00:00Z");
seedConsumptionRecord(2, "300.0000", "2026-08-12T08:00:00Z");
seedConsumptionRecord(3, "500.0000", "2026-08-18T08:00:00Z");

// ---------------------------------------------------------------------------
// The client
// ---------------------------------------------------------------------------

export const mockClient: ApiClient = {
  async register(req: RegisterRequest): Promise<User> {
    await delay();
    if (!notEmpty(req.email) || !notEmpty(req.password)) {
      throw new ApiError("VALIDATION_ERROR", "email and password must not be empty", 422);
    }
    if (req.password.length < 8) {
      throw new ApiError("VALIDATION_ERROR", "password must be at least 8 characters", 422);
    }
    if (users.some((u) => u.email === req.email)) {
      throw new ApiError("EMAIL_ALREADY_REGISTERED", `Email ${req.email} is already registered`, 422);
    }
    const user: MockUser = { id: nextUserId++, email: req.email, password: req.password, created_at: nowIso() };
    users.push(user);
    return { id: user.id, email: user.email, created_at: user.created_at };
  },

  async login(req: LoginRequest) {
    await delay();
    const user = users.find((u) => u.email === req.email && u.password === req.password);
    if (!user) {
      throw new ApiError("INVALID_CREDENTIALS", "Incorrect email or password", 401);
    }
    return { access_token: `mock-token-${user.id}-${Date.now()}`, token_type: "bearer" };
  },

  async createOrganization(req: OrganizationCreateRequest) {
    await delay();
    if (!notEmpty(req.name) || !notEmpty(req.industry_type)) {
      throw new ApiError("VALIDATION_ERROR", "name and industry_type must not be empty", 422);
    }
    const org: Organization = {
      id: nextId.organization++,
      name: req.name.trim(),
      industry_type: req.industry_type.trim(),
      created_at: nowIso(),
    };
    organizations.push(org);
    return org;
  },

  async getOrganization(id: number) {
    await delay();
    return requireOrganization(id);
  },

  async listOrganizations() {
    await delay();
    // The mock has a single implicit tenant, so every organization it holds
    // belongs to the caller. Sorted by name to match the ordering the real
    // endpoint guarantees, so the picker looks the same in both modes.
    return [...organizations].sort(
      (a, b) => a.name.localeCompare(b.name) || a.id - b.id,
    );
  },

  async createFacility(req: FacilityCreateRequest) {
    await delay();
    requireOrganization(req.organization_id);
    if (!notEmpty(req.name) || !notEmpty(req.location) || !notEmpty(req.facility_type)) {
      throw new ApiError("VALIDATION_ERROR", "name, location and facility_type must not be empty", 422);
    }
    const now = nowIso();
    const facility: Facility = {
      id: nextId.facility++,
      organization_id: req.organization_id,
      name: req.name.trim(),
      location: req.location.trim(),
      facility_type: req.facility_type.trim(),
      created_at: now,
      updated_at: now,
    };
    facilities.push(facility);
    return facility;
  },

  async listFacilities(organizationId: number) {
    await delay();
    return facilities.filter((f) => f.organization_id === organizationId);
  },

  async createEmissionSource(req: EmissionSourceCreateRequest) {
    await delay();
    requireFacility(req.facility_id);
    if (!SOURCE_TYPES.includes(req.source_type)) {
      throw new ApiError("VALIDATION_ERROR", `source_type must be one of ${SOURCE_TYPES.join(", ")}`, 422);
    }
    if (!notEmpty(req.source_name) || !notEmpty(req.unit_of_measurement)) {
      throw new ApiError("VALIDATION_ERROR", "source_name and unit_of_measurement must not be empty", 422);
    }
    const now = nowIso();
    const source: EmissionSource = {
      id: nextId.emissionSource++,
      facility_id: req.facility_id,
      source_type: req.source_type,
      source_name: req.source_name.trim(),
      unit_of_measurement: req.unit_of_measurement.trim(),
      barcode_value: req.barcode_value?.trim() || null,
      created_at: now,
      updated_at: now,
    };
    emissionSources.push(source);
    return source;
  },

  async listEmissionSources(facilityId: number) {
    await delay();
    return emissionSources.filter((s) => s.facility_id === facilityId);
  },

  async scanAsset(facilityId: number, _image: Blob): Promise<AssetScanResult> {
    await delay();
    requireFacility(facilityId);
    // The mock has no real image-decoding capability (no barcode/QR library
    // in this project, and adding one just for mock-mode fidelity isn't
    // worth it — the real decode path is only meaningfully testable against
    // the real backend anyway). Simulate the common happy path instead:
    // "scanning" always resolves to whichever seeded source in this
    // facility has a barcode_value assigned. If none do, simulate the
    // real "nothing readable" case so the UI's error path is still
    // exercisable in mock mode.
    const source = emissionSources.find((s) => s.facility_id === facilityId && s.barcode_value);
    if (!source || !source.barcode_value) {
      throw new ApiError("NO_BARCODE_DETECTED", "No readable barcode found in frame", 422);
    }
    return {
      decoded_value: source.barcode_value,
      bounding_box: { x: 120, y: 84, width: 220, height: 96 },
      emission_source: source,
    };
  },

  async listEmissionFactors(filters?: EmissionFactorFilters) {
    await delay();
    return emissionFactors.filter(
      (f) =>
        (!filters?.source_type || f.source_type === filters.source_type) &&
        (!filters?.region || f.region === filters.region),
    );
  },

  async createConsumptionRecord(req: ConsumptionRecordCreateRequest) {
    await delay();
    const source = requireEmissionSource(req.emission_source_id);
    requireFacility(req.facility_id);

    const asOfDate = req.recorded_at.slice(0, 10);
    const factor = findApplicableFactor(source.source_type, asOfDate);
    if (!factor) {
      throw new ApiError(
        "NO_MATCHING_FACTOR",
        `No emission factor found for source_type=${source.source_type} region=${DEFAULT_REGION} as of ${asOfDate}`,
        422,
      );
    }

    const record: ConsumptionRecord = {
      id: nextId.consumptionRecord++,
      emission_source_id: req.emission_source_id,
      facility_id: req.facility_id,
      quantity_consumed: req.quantity_consumed,
      unit: req.unit,
      recorded_at: req.recorded_at,
      created_at: nowIso(),
      calculation: {
        id: nextId.calculation++,
        emission_factor_id: factor.id,
        calculated_emissions_kg_co2e: multiply(req.quantity_consumed, factor.factor_value),
        calculation_date: todayDate(),
      },
    };
    consumptionRecords.push(record);
    return record;
  },

  async listConsumptionRecords(filters: ConsumptionRecordFilters) {
    await delay();
    return consumptionRecords
      .filter((r) => {
        if (r.facility_id !== filters.facility_id) return false;
        const d = r.recorded_at.slice(0, 10);
        if (filters.start_date && d < filters.start_date) return false;
        if (filters.end_date && d > filters.end_date) return false;
        return true;
      })
      .sort((a, b) => (a.recorded_at < b.recorded_at ? 1 : -1));
  },

  async getEmissionsSummary(facilityId: number, filters: EmissionsSummaryFilters) {
    await delay();
    requireFacility(facilityId);
    const bySourceType = sumBySourceType(facilityId, filters.start_date, filters.end_date);
    const total = SOURCE_TYPES.reduce((sum, type) => sum + parseFloat(bySourceType[type]), 0);
    const summary: EmissionsSummary = {
      facility_id: facilityId,
      period: { start: filters.start_date, end: filters.end_date },
      total_emissions_kg_co2e: total.toFixed(2),
      by_source_type: bySourceType,
    };
    return summary;
  },

  async getOrganizationOverview(organizationId: number, filters: EmissionsSummaryFilters) {
    await delay();
    const org = requireOrganization(organizationId);
    // Built from the same sumBySourceType() the mock's REST summary uses, so
    // the overview page and the dashboard cannot disagree in mock mode for
    // the same reason they cannot disagree against the real backend: one
    // calculation, two views onto it.
    return {
      id: org.id,
      name: org.name,
      industryType: org.industry_type,
      facilities: facilities
        .filter((f) => f.organization_id === organizationId)
        .map((f) => {
          const bySourceType = sumBySourceType(f.id, filters.start_date, filters.end_date);
          const total = SOURCE_TYPES.reduce(
            (sum, type) => sum + parseFloat(bySourceType[type]),
            0,
          );
          return {
            id: f.id,
            name: f.name,
            location: f.location,
            emissionsSummary: {
              facilityId: f.id,
              periodStart: filters.start_date,
              periodEnd: filters.end_date,
              totalEmissionsKgCo2e: total.toFixed(2),
              bySourceType,
            },
          };
        }),
    };
  },

  async generateReport(req: ReportGenerateRequest) {
    await delay();
    requireOrganization(req.organization_id);
    const { total, facilityBreakdown } = reportBreakdown(
      req.organization_id,
      req.report_period_start,
      req.report_period_end,
    );
    const report: Report = {
      id: nextId.report++,
      organization_id: req.organization_id,
      report_period_start: req.report_period_start,
      report_period_end: req.report_period_end,
      generated_at: nowIso(),
      status: "final",
      total_emissions_kg_co2e: total,
      facilities: facilityBreakdown,
    };
    reports.push(report);
    return report;
  },

  async getReport(id: number) {
    await delay();
    const report = reports.find((r) => r.id === id);
    if (!report) throw new ApiError("NOT_FOUND", `Report ${id} does not exist`, 404);
    return report;
  },

  async listReports(organizationId: number) {
    await delay();
    return reports
      .filter((r) => r.organization_id === organizationId)
      .map(toSummary)
      .sort((a, b) => (a.generated_at < b.generated_at ? 1 : -1));
  },
};
