import type { Locator, Page } from "@playwright/test";
import { BasePage } from "../BasePage";

/**
 * Page Object Model for the dataset detail page at `/datasets/:id`.
 *
 * Covers the Samples tab: sample browser grid/list, sidebar toggle,
 * sample detail drawer, and embedded wafer map panel.
 */
export class DatasetSamplesPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async waitForLoaded(): Promise<void> {
    await this.page.waitForSelector("[data-sb-item]");
  }

  // ── View mode ────────────────────────────────────────────────────

  getGridRadio(): Locator {
    return this.page.getByRole("radio", { name: "Grid" });
  }

  getListRadio(): Locator {
    return this.page.getByRole("radio", { name: "List" });
  }

  // ── Sidebar ──────────────────────────────────────────────────────

  getSidebarToggle(): Locator {
    return this.page.locator(".cs-header__toggle");
  }

  // ── Sample browser ───────────────────────────────────────────────

  getSampleBrowserItems(): Locator {
    return this.page.locator("[data-sb-item]");
  }

  async goToClassify(datasetId: string): Promise<this> {
    await this.goto(`/datasets/${datasetId}/classify`);
    await this.waitForLoaded();
    return this;
  }

  async clickFirstSample(): Promise<void> {
    await this.getSampleBrowserItems().first().click();
  }

  // ── Sample detail ────────────────────────────────────────────────

  getSampleDetail(): Locator {
    return this.page.getByText("Sample Detail");
  }

  // ── Wafer map ────────────────────────────────────────────────────

  getWaferMapPanel(): Locator {
    return this.page.locator('[data-testid="wafer-map-panel"]');
  }

  getWaferMapCanvas(): Locator {
    return this.page.locator('[data-testid="wafer-map-panel"] canvas');
  }
}
