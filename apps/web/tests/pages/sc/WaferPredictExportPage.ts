import type { Locator, Page } from '@playwright/test';
import { BasePage } from '../BasePage';

/**
 * Page Object Model for the SC prediction + export phases.
 *
 * Covers:
 * - `/datasets/:id/classify` — classify page
 * - Prediction card with model selector and "Run Predictions" button
 * - `/datasets/:id` — dataset detail view
 * - Export tab with "Export Dataset" button and "Persist Export" flow
 */
export class WaferPredictExportPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async waitForLoaded(): Promise<void> {
    await this.page.locator('.classify-page').waitFor({ timeout: 10_000 });
  }

  // ── Navigation ──────────────────────────────────────────────────

  async goToClassify(datasetId: string): Promise<this> {
    await this.goto(`/datasets/${datasetId}/classify`);
    await this.waitForLoaded();
    return this;
  }

  async goToDatasetView(datasetId: string): Promise<this> {
    await this.goto(`/datasets/${datasetId}`);
    await this.page
      .locator('[data-testid="view-sc-patch-image"]')
      .waitFor({ timeout: 10_000 });
    return this;
  }

  // ── Prediction card ─────────────────────────────────────────────

  get predictionCard(): Locator {
    return this.page.getByTestId('classify-prediction-card');
  }

  get modelSelectTrigger(): Locator {
    return this.predictionCard.locator('.n-base-selection').first();
  }

  get runPredictionsButton(): Locator {
    return this.page.getByRole('button', { name: 'Run Predictions' });
  }

  get activePredictionText(): Locator {
    return this.predictionCard.locator('.n-text');
  }

  async waitForPredictionCard(): Promise<this> {
    await this.predictionCard.waitFor({ timeout: 10_000 });
    return this;
  }

  /**
   * Open the model dropdown and select a model by ID text.
   * Falls back to the first option if the model is not found.
   */
  async selectModel(modelId: string): Promise<this> {
    await this.modelSelectTrigger.click();
    await this.page
      .locator('.n-base-select-option')
      .first()
      .waitFor({ timeout: 5_000 });
    const option = this.page
      .locator('.n-base-select-option')
      .filter({ hasText: modelId });
    if ((await option.count()) > 0) {
      await option.first().click();
    } else {
      await this.page.locator('.n-base-select-option').first().click();
    }
    return this;
  }

  async clickRunPredictions(): Promise<this> {
    await this.runPredictionsButton.click();
    return this;
  }

  /**
   * Parse the prediction job ID from the active prediction text.
   * Expected format: "Active prediction: {id} ({status})"
   */
  async getActivePredictionJobId(): Promise<string | null> {
    const text = await this.activePredictionText.innerText().catch(() => '');
    const match = text.match(/Active prediction:\s*(\S+)/);
    return match ? match[1] : null;
  }

  // ── Export ──────────────────────────────────────────────────────

  get exportTab(): Locator {
    return this.page.getByRole('tab', { name: 'Export' });
  }

  get exportDatasetButton(): Locator {
    return this.page.getByRole('button', { name: 'Export Dataset' });
  }

  get exportModal(): Locator {
    return this.page.locator('.n-modal').filter({ hasText: 'Export Dataset' });
  }

  get persistExportCard(): Locator {
    return this.page.getByText('Persist Export', { exact: true });
  }

  get persistExportActionButton(): Locator {
    return this.page.getByRole('button', { name: 'Persist Export', exact: true });
  }

  get exportSuccessAlert(): Locator {
    return this.page.getByText(/Export persisted:/);
  }

  get doneButton(): Locator {
    return this.page.getByRole('button', { name: 'Done' });
  }

  async clickExportTab(): Promise<this> {
    await this.exportTab.click();
    return this;
  }

  async clickExportDataset(): Promise<this> {
    await this.exportDatasetButton.click();
    return this;
  }

  async waitForExportModal(): Promise<this> {
    await this.exportModal.waitFor({ timeout: 5_000 });
    return this;
  }

  async clickPersistExportCard(): Promise<this> {
    await this.persistExportCard.click();
    return this;
  }

  async clickPersistExportAction(): Promise<this> {
    await this.persistExportActionButton.click();
    return this;
  }

  async waitForExportSuccess(): Promise<this> {
    await this.exportSuccessAlert.waitFor({ timeout: 30_000 });
    return this;
  }

  async clickDone(): Promise<this> {
    await this.doneButton.click();
    return this;
  }
}
