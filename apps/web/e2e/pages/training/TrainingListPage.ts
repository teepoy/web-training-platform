import type { Locator, Page } from "@playwright/test";
import { BasePage } from "../BasePage";

/**
 * Page Object Model for the Training Jobs list view at `/jobs`.
 */
export class TrainingListPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async waitForLoaded(): Promise<void> {
    await this.page.waitForSelector(".n-data-table");
  }

  async goto(): Promise<void> {
    await this.page.goto("/jobs");
    await this.waitForLoaded();
  }

  /** Click "Start New Job" to open the creation dialog. */
  async clickStartNewJob(): Promise<void> {
    await this.page.getByRole("button", { name: "Start New Job" }).click();
    await this.creationDialog.waitFor({ state: "visible" });
  }

  /** Locator for the new-job creation dialog. */
  get creationDialog(): Locator {
    return this.page.getByRole("dialog");
  }

  /** Select a dataset by name inside the creation dialog. */
  async selectDataset(name: string): Promise<void> {
    await this.creationDialog
      .locator(".n-base-selection")
      .filter({ hasText: "Select a dataset" })
      .first()
      .click();
    await this.page.locator(".n-base-select-option").filter({ hasText: name }).click();
  }

  /** Select the first available trainer in the creation dialog. */
  async selectFirstTrainer(): Promise<void> {
    await this.creationDialog
      .locator(".n-base-selection")
      .filter({ hasText: "Select a trainer" })
      .first()
      .click();
    await this.page.locator(".n-base-select-option:visible").first().click();
  }

  /** Click the "Start" button in the creation dialog. */
  async clickStart(): Promise<void> {
    await this.creationDialog.getByRole("button", { name: "Start", exact: true }).click();
  }

  /** Wait for the "Job started" success toast. */
  async waitForJobStarted(): Promise<void> {
    await this.page
      .locator(".n-message")
      .filter({ hasText: "Job started" })
      .waitFor({ state: "visible", timeout: 15000 });
  }

  /** Click the "View" button on the job row matching a dataset name. */
  async viewJobForDataset(datasetName: string): Promise<void> {
    const row = this.page.locator(".n-data-table tr", {
      has: this.page.getByText(datasetName),
    });
    await row.waitFor({ state: "visible", timeout: 10000 });
    await row.getByRole("button", { name: "View" }).click();
  }

  /** Wait for an SSE connection tag to appear (visible on job detail). */
  async waitForSseOpen(): Promise<void> {
    await this.page.locator(".n-tag").filter({ hasText: /SSE:/ }).waitFor({
      state: "visible",
      timeout: 30000,
    });
    await this.page.getByText("SSE: open").waitFor({ state: "visible", timeout: 30000 });
  }

  /** Locator for the "Training Progress" card on the job detail page. */
  get trainingProgressCard(): Locator {
    return this.page.getByTestId("job-training-progress-card");
  }

  /** Locator for a completed-status job row (first match). */
  get completedJobRow(): Locator {
    return this.page.locator(".n-data-table tr", {
      has: this.page.getByText("completed"),
    });
  }
}
