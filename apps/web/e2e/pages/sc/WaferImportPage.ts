import type { Locator, Page } from "@playwright/test";
import { BasePage } from "../BasePage";
import { E2E_TIMEOUTS } from "../../timeouts";

/**
 * Page Object Model for the SC import workflow.
 *
 * Covers:
 * - `/sc/preview` — SC preview page with search bar and inspection table
 * - Inspection page (opened in a new browser tab by clicking a table row)
 * - Reclassify import
 * - Open `/datasets/:id/sc/classify` on completion
 */
export class WaferImportPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async waitForLoaded(): Promise<void> {
    await this.page.locator(".sc-preview").waitFor({ timeout: 10_000 });
  }

  // ── Navigation ──────────────────────────────────────────────────

  async goToScPreview(): Promise<this> {
    await this.goto("/sc/preview");
    await this.waitForLoaded();
    return this;
  }

  // ── Search bar ──────────────────────────────────────────────────

  get startTimePicker(): Locator {
    return this.page.getByPlaceholder("Start Date");
  }

  get endTimePicker(): Locator {
    return this.page.getByPlaceholder("End Date");
  }

  get searchButton(): Locator {
    return this.page.getByRole("button", { name: "Search" });
  }

  async fillTimeRange(startTime: string, endTime: string): Promise<this> {
    // The preview search uses a date-range picker. Callers still pass the
    // historical date-time values, so keep this POM boundary compatible.
    // Its end value is an exclusive midnight boundary; advance it by one day
    // so a caller's end date remains included in the search.
    const exclusiveEnd = new Date(`${endTime.slice(0, 10)}T00:00:00Z`);
    exclusiveEnd.setUTCDate(exclusiveEnd.getUTCDate() + 1);

    await this.startTimePicker.fill(startTime.slice(0, 10));
    await this.endTimePicker.fill(exclusiveEnd.toISOString().slice(0, 10));
    await this.endTimePicker.press("Tab");
    return this;
  }

  async clickSearch(): Promise<this> {
    await this.searchButton.click();
    return this;
  }

  // ── Inspection table ────────────────────────────────────────────

  get dataTable(): Locator {
    return this.page.locator(".n-data-table");
  }

  get firstRow(): Locator {
    return this.page.locator(".n-data-table tbody tr").first();
  }

  async waitForTableRows(): Promise<this> {
    await this.dataTable.waitFor({ timeout: 15_000 });
    await this.firstRow.waitFor({ timeout: 15_000 });
    return this;
  }

  async openFirstInspection(): Promise<this> {
    const popupPromise = this.page.waitForEvent("popup");
    await this.firstRow.click();
    const popup = await popupPromise;
    await popup.waitForURL(/\/sc\/inspections\//, { timeout: 10_000 });

    // Continue in the fixture's primary page after verifying the application
    // opened the dedicated inspection route in a new browser tab.
    const inspectionUrl = popup.url();
    await popup.close();
    await this.page.goto(inspectionUrl);
    await this.inspectionPage.waitFor({ timeout: 10_000 });
    return this;
  }

  // ── Inspection page ─────────────────────────────────────────────

  get inspectionPage(): Locator {
    return this.page.locator(".sc-inspection-page");
  }

  get reclassifyButton(): Locator {
    return this.page.getByRole("button", { name: "Reclassify" });
  }

  async clickReclassify(): Promise<this> {
    await this.reclassifyButton.click();
    return this;
  }

  get openDatasetLink(): Locator {
    return this.page.getByRole("link", { name: "Open Dataset" });
  }

  // ── Completion ──────────────────────────────────────────────────

  /**
   * Wait for the import to complete and the page to redirect to
   * `/datasets/:id/sc/classify`. Returns the classify page URL.
   */
  async waitForImportCompletion(timeoutMs = E2E_TIMEOUTS.operation.scImport): Promise<string> {
    await this.openDatasetLink.waitFor({ timeout: timeoutMs });
    const classifyPath = await this.openDatasetLink.getAttribute("href");
    if (!classifyPath) throw new Error("Open Dataset link is missing its href");
    await this.page.goto(classifyPath);
    await this.page.waitForURL("**/datasets/**/sc/classify", {
      timeout: E2E_TIMEOUTS.navigation,
    });
    await this.page
      .locator(".sc-classify-page")
      .waitFor({ timeout: E2E_TIMEOUTS.operation.scDataLoad });
    return this.page.url();
  }

  /**
   * Extract the dataset ID from a `/datasets/:id/sc/classify` URL.
   */
  extractDatasetId(url: string): string | null {
    return url.match(/\/datasets\/([^/]+)\/sc\/classify/)?.[1] ?? null;
  }
}
