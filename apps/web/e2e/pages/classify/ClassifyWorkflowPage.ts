import type { Locator, Page } from "@playwright/test";
import { BasePage } from "../BasePage";

/**
 * Page Object Model for the classify workflow page at `/datasets/:id/classify`.
 *
 * Covers the prediction review flow: sample browser, model selection,
 * prediction execution, review mode grid, and wafer map panel.
 */
export class ClassifyWorkflowPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async waitForLoaded(): Promise<void> {
    await this.page.getByRole("button", { name: "Run Predictions" }).waitFor();
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

  // ── Model selection ──────────────────────────────────────────────

  /**
   * Select a model from the model dropdown.
   *
   * Opens the Naive UI base selection, then picks the option
   * whose text contains the given model name.
   */
  async selectModel(name: string): Promise<void> {
    await this.page
      .locator(".n-base-selection")
      .filter({ hasText: "Select model" })
      .first()
      .click();
    await this.page
      .locator(".n-base-select-option")
      .filter({ hasText: new RegExp(name) })
      .click();
  }

  // ── Prediction ───────────────────────────────────────────────────

  getRunPredictionsButton(): Locator {
    return this.page.getByRole("button", { name: "Run Predictions" });
  }

  async clickRunPredictions(): Promise<void> {
    await this.getRunPredictionsButton().click();
  }

  getPredictionSubmittedMessage(): Locator {
    return this.page.getByText(/Prediction job submitted:/);
  }

  getReviewReadyMessage(): Locator {
    return this.page.getByText(/predictions ready for review/);
  }

  getPredictionReviewMode(): Locator {
    return this.page.getByText("Prediction Review Mode");
  }

  getAgGrid(): Locator {
    return this.page.locator(".ag");
  }

  getSubmitButton(): Locator {
    return this.page.getByRole("button", { name: /Submit \d+/ });
  }

  // ── Wafer map ────────────────────────────────────────────────────

  getWaferMapPanel(): Locator {
    return this.page.locator('[data-testid="wafer-map-panel"]');
  }

  getWaferMapCanvas(): Locator {
    return this.page.locator('[data-testid="wafer-map-panel"] canvas');
  }

  getChartWrap(): Locator {
    return this.page.locator('[data-testid="wafer-map-panel"] .wmw-chart-wrap');
  }

  getWaferMapFooter(): Locator {
    return this.page.locator('[data-testid="wafer-map-panel"] .wmw-footer');
  }

  // ── Zoom ─────────────────────────────────────────────────────────

  getResetZoomButton(): Locator {
    return this.page
      .locator('[data-testid="wafer-map-panel"]')
      .getByRole("button", { name: "Reset Zoom" });
  }

  /**
   * Dispatch a wheel event on the chart area to trigger zoom.
   */
  async simulateZoom(): Promise<void> {
    await this.page.evaluate(() => {
      const wrapper = document.querySelector('[data-testid="wafer-map-panel"] .wmw-chart-wrap');
      if (!wrapper) return;
      const rect = wrapper.getBoundingClientRect();
      wrapper.dispatchEvent(
        new WheelEvent("wheel", {
          deltaY: -100,
          deltaX: 0,
          clientX: rect.left + rect.width / 2,
          clientY: rect.top + rect.height / 2,
          bubbles: true,
          cancelable: true,
        }),
      );
    });
  }

  async clickResetZoom(): Promise<void> {
    await this.getResetZoomButton().click();
  }
}
