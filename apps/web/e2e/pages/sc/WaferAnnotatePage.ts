import type { Locator, Page } from "@playwright/test";
import { BasePage } from "../BasePage";
import { E2E_TIMEOUTS } from "../../timeouts";

/**
 * Page Object Model for the current SC reclassify workspace.
 *
 * Covers:
 * - `/datasets/:id/sc/classify` — map, table, gallery, and annotation sidebar
 */
export class WaferAnnotatePage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async waitForLoaded(): Promise<void> {
    await this.classifyPage.waitFor({ timeout: E2E_TIMEOUTS.expect });
  }

  // ── Navigation ──────────────────────────────────────────────────

  async goToClassify(datasetId: string): Promise<this> {
    await this.goto(`/datasets/${datasetId}/sc/classify`);
    await this.waitForLoaded();
    return this;
  }

  // ── Classify page ───────────────────────────────────────────────

  get classifyPage(): Locator {
    return this.page.locator(".sc-classify-page");
  }

  get sampleBrowserItems(): Locator {
    return this.page.locator(".sbt-sample-block");
  }

  get mapPanel(): Locator {
    return this.page.getByTestId("sc-map-panel");
  }

  get sampleTable(): Locator {
    return this.page.locator(".vxe-table");
  }

  // ── Annotation ──────────────────────────────────────────────────

  get annotationGrid(): Locator {
    return this.page.getByTestId("reclassify-code-list");
  }

  /** Get a label button by text in the annotation sidebar. */
  getLabelButton(label: string): Locator {
    return this.page.locator(".sc-code-button").filter({ hasText: label });
  }

  async waitForSamples(): Promise<this> {
    await this.sampleBrowserItems.first().waitFor({ timeout: E2E_TIMEOUTS.operation.scDataLoad });
    return this;
  }
}
