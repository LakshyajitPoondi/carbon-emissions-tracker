import { test, expect, type Page } from "@playwright/test";
import type { ConsumptionRecord, Product } from "../src/types";

// Isolated browser + deterministic API responses. Real PNG decode, persistence,
// Decimal arithmetic, authorization and aggregation are covered in pytest.
async function prepare(page: Page, options: { configured?: boolean; sources?: boolean; fail?: boolean; manage?: boolean } = {}) {
  const organization = { id: 701, name: "Browser Test Organization", industry_type: "manufacturing", role: options.manage ? "OWNER" : "EMPLOYEE", created_at: "2026-09-01T00:00:00Z" };
  const facility = { id: 702, organization_id: 701, name: "Browser Test Plant", location: "Test", facility_type: "factory", created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z" };
  let product: Product = {
    id: 703, organization_id: 701, name: "Recycled Aluminium Bottle", barcode: "2000000000039",
    composition: "70% recycled aluminium, 30% primary aluminium", emissions_value: "1.250000",
    emissions_unit: "kg CO2e/item", emissions_description: "Test embodied emissions per bottle",
    source_reference: "Test supplier EPD, 2026", consumption_unit: options.configured === false ? null : "item",
    consumption_source_type: options.configured === false ? null : "RESOURCE",
    created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z",
  };
  const records: ConsumptionRecord[] = [];
  const writes: Record<string, unknown>[] = [];
  let failNext = Boolean(options.fail);
  await page.addInitScript(({ organization, facility }) => {
    localStorage.setItem("cfp.auth.token", "isolated-browser-test-token");
    localStorage.setItem("cfp.auth.email", "employee@test.invalid");
    localStorage.setItem("cfp.selection", JSON.stringify({ organization, facility }));
  }, { organization, facility });
  await page.route(/^http:\/\/127\.0\.0\.1:8000\/api\//, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const respond = (json: unknown, status = 200) => route.fulfill({ status, json });
    if (url.pathname === "/api/organizations") return respond([organization]);
    if (url.pathname.endsWith("/asset-scan")) return respond({ match_type: "product", data: product });
    if (url.pathname === "/api/emission-sources") return respond(options.sources === false ? [] : [{
      id: 704, facility_id: facility.id, source_type: "FUEL", source_name: "Unrelated diesel source",
      unit_of_measurement: "litre", barcode_value: null, created_at: product.created_at, updated_at: product.updated_at,
    }]);
    if (url.pathname === "/api/consumption-records") {
      if (request.method() === "GET") return respond(records);
      const body = request.postDataJSON();
      writes.push(body);
      if (failNext) {
        failNext = false;
        return respond({ error: { code: "PRODUCT_UNIT_MISMATCH", message: "This Product must be logged in item" } }, 422);
      }
      const { organization_id: _organizationId, composition: _composition, created_at: _created, updated_at: _updated, ...snapshot } = product;
      const record = {
        ...body, id: records.length + 1, emission_source_id: body.emission_source_id ?? null,
        product_id: body.product_id ?? null,
        product_snapshot: body.product_id ? snapshot : null,
        created_at: new Date().toISOString(),
        calculation: { id: records.length + 1, emission_factor_id: body.product_id ? null : 3,
          calculated_emissions_kg_co2e: (Number(body.quantity_consumed) * (body.product_id ? 1.25 : 2.683)).toFixed(4),
          calculation_date: body.recorded_at.slice(0, 10) },
      } as ConsumptionRecord;
      records.push(record);
      return respond(record, 201);
    }
    if (url.pathname.endsWith("/emissions-summary")) {
      const total = records.reduce((sum, record) => sum + Number(record.calculation!.calculated_emissions_kg_co2e), 0).toFixed(2);
      return respond({ facility_id: facility.id, period: { start: url.searchParams.get("start_date"), end: url.searchParams.get("end_date") },
        total_emissions_kg_co2e: total, by_source_type: { ENERGY: "0.00", FUEL: "0.00", RESOURCE: total } });
    }
    if (url.pathname === "/api/products") return respond([product]);
    if (url.pathname === `/api/products/${product.id}` && request.method() === "PATCH") {
      product = { ...product, ...request.postDataJSON() };
      return respond(product);
    }
    // Never let a test write to the real development API by accident.
    return respond({ error: { code: "NOT_FOUND", message: "Unmocked test route" } }, 404);
  });
  await page.goto("/consumption");
  await expect(page.getByRole("heading", { name: "Log Consumption", exact: true })).toBeVisible();
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
  return { writes, records, organization };
}

async function scan(page: Page) {
  await page.getByRole("button", { name: "Scan Barcode", exact: true }).click();
  await expect.poll(() => page.locator("video").evaluate((video: HTMLVideoElement) => video.readyState)).toBeGreaterThanOrEqual(2);
  await page.getByRole("button", { name: "Capture", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Product matched" })).toBeVisible();
  return page.getByRole("form", { name: "Log matched product" });
}

test("matched-card button saves the Product once, refreshes Recent records and Dashboard", async ({ page }, testInfo) => {
  const { writes } = await prepare(page);
  const form = await scan(page);
  await expect(form.getByLabel("Product quantity (item)")).toHaveValue("1");
  await form.getByLabel("Product quantity (item)").fill("2");
  await expect(form.getByLabel("Product quantity (item)")).toHaveValue("2");
  expect(await form.evaluate((element: HTMLFormElement) => element.checkValidity())).toBe(true);
  const logButton = form.getByRole("button", { name: "Log consumption", exact: true });
  await logButton.scrollIntoViewIfNeeded();
  await expect(logButton).toBeInViewport({ ratio: 1 });
  await logButton.click();
  await expect(form.getByRole("button", { name: "Consumption logged" })).toBeDisabled();
  await expect(form).toContainText("2.5000 kg CO2e");
  expect(writes).toHaveLength(1);
  expect(writes[0]).toMatchObject({ product_id: 703, facility_id: 702, quantity_consumed: "2", unit: "item" });
  expect(writes[0]).not.toHaveProperty("emission_source_id");
  await expect(page.getByRole("cell", { name: "Recycled Aluminium Bottle (Product)" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("product-logged.png"), fullPage: true });
  await form.getByRole("link", { name: "View Dashboard" }).click();
  await expect(page.locator(".bar-chart__row").filter({ hasText: "Scope 3" }).locator(".bar-chart__value")).toHaveText("2.50 kg CO2e");
  await page.screenshot({ path: testInfo.outputPath("dashboard-product-total.png"), fullPage: true });
});

test("Product logging works when the facility has no emission sources", async ({ page }) => {
  const { writes } = await prepare(page, { sources: false });
  const form = await scan(page);
  await form.getByRole("button", { name: "Log consumption", exact: true }).click();
  await expect(form.getByRole("button", { name: "Consumption logged" })).toBeDisabled();
  expect(writes).toHaveLength(1);
});

test("unconfigured Products explain setup and cannot be logged", async ({ page }) => {
  const { writes } = await prepare(page, { configured: false });
  const form = await scan(page);
  await expect(form).toContainText("Ask an OWNER or ADMIN");
  await expect(form.getByRole("button", { name: "Log consumption", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Done", exact: true }).click();
  expect(writes).toHaveLength(0);
});

test("API failures remain in the card and allow an explicit retry", async ({ page }) => {
  const { writes, records } = await prepare(page, { fail: true });
  const form = await scan(page);
  await form.getByRole("button", { name: "Log consumption", exact: true }).click();
  await expect(form).toContainText("PRODUCT_UNIT_MISMATCH");
  expect(records).toHaveLength(0);
  await form.getByRole("button", { name: "Log consumption", exact: true }).click();
  await expect(form.getByRole("button", { name: "Consumption logged" })).toBeDisabled();
  expect(writes).toHaveLength(2);
  expect(records).toHaveLength(1);
});

test("manual source logging retains its original request", async ({ page }) => {
  const { writes } = await prepare(page);
  await page.getByLabel("Quantity consumed (litre)", { exact: true }).fill("3");
  await page.getByRole("button", { name: "Log consumption", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Emissions calculated" })).toBeVisible();
  expect(writes[0]).toMatchObject({ emission_source_id: 704, unit: "litre", quantity_consumed: "3" });
  expect(writes[0]).not.toHaveProperty("product_id");
});

test("mock client logs Product factors and preserves history after deletion", async ({ page }) => {
  await prepare(page);
  const result = await page.evaluate(async () => {
    // Vite serves the real mock adapter in this isolated browser, without
    // switching the user's .env.local or touching the live database.
    const modulePath = "/src/api/mockClient.ts";
    const { mockClient } = await import(modulePath);
    const product = await mockClient.createProduct({
      organization_id: 1, name: "Mock fixture", composition: "Test", emissions_value: "1.25",
      emissions_unit: "kg CO2e/item", consumption_unit: "item", consumption_source_type: "RESOURCE",
      emissions_description: "Test figure", source_reference: "Test fixture",
    });
    const record = await mockClient.createConsumptionRecord({ product_id: product.id, facility_id: 1,
      quantity_consumed: "2", unit: "item", recorded_at: "2026-09-03T12:00:00Z" });
    await mockClient.deleteProduct(product.id);
    const summary = await mockClient.getEmissionsSummary(1, { start_date: "2026-09-03", end_date: "2026-09-03" });
    return { record, summary };
  });
  expect(result.record.product_id).toBeNull();
  expect(result.record.product_snapshot.name).toBe("Mock fixture");
  expect(result.summary.by_source_type.RESOURCE).toBe("2.50");
});

test("OWNER can configure a reference-only Product and then log it from the card", async ({ page }) => {
  const { writes } = await prepare(page, { configured: false, manage: true });
  await page.getByRole("link", { name: "Products", exact: true }).click();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel("Consumption scope (optional)").selectOption("RESOURCE");
  await page.getByLabel("Consumption unit", { exact: true }).fill("item");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByText("Updated Recycled Aluminium Bottle.", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Consumption", exact: true }).click();
  const form = await scan(page);
  await form.getByRole("button", { name: "Log consumption", exact: true }).click();
  await expect(form.getByRole("button", { name: "Consumption logged" })).toBeDisabled();
  expect(writes).toHaveLength(1);
});
