import type { Locator, Page } from '@playwright/test';
import { BasePage } from '../BasePage';

/**
 * Page Object Model for the SC training phase on the classify page.
 *
 * Covers:
 * - `/datasets/:id/classify` — classify page
 * - Training card with trainer selector and "Start Training" button
 * - Training job monitoring (polling via API helpers)
 */
export class WaferTrainingPage extends BasePage {
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

  // ── Training card ───────────────────────────────────────────────

  get trainingCard(): Locator {
    return this.page.getByTestId('classify-training-card');
  }

  get trainerSelectTrigger(): Locator {
    return this.trainingCard.locator('.n-base-selection').first();
  }

  get startTrainingButton(): Locator {
    return this.page.getByRole('button', { name: 'Start Training' });
  }

  get activeTrainingText(): Locator {
    return this.trainingCard.locator('.n-text');
  }

  async waitForTrainingCard(): Promise<this> {
    await this.trainingCard.waitFor({ timeout: 10_000 });
    return this;
  }

  /**
   * Open the trainer dropdown and select the first available trainer.
   */
  async selectFirstTrainer(): Promise<this> {
    await this.trainerSelectTrigger.click();
    await this.page
      .locator('.n-base-select-option')
      .first()
      .waitFor({ timeout: 5_000 });
    await this.page.locator('.n-base-select-option').first().click();
    return this;
  }

  /**
   * Select a trainer by name text contained in the dropdown option.
   */
  async selectTrainer(name: string): Promise<this> {
    await this.trainerSelectTrigger.click();
    await this.page
      .locator('.n-base-select-option')
      .first()
      .waitFor({ timeout: 5_000 });
    const option = this.page
      .locator('.n-base-select-option')
      .filter({ hasText: name });
    if ((await option.count()) > 0) {
      await option.first().click();
    } else {
      // Fall back to first option
      await this.page.locator('.n-base-select-option').first().click();
    }
    return this;
  }

  async clickStartTraining(): Promise<this> {
    await this.startTrainingButton.click();
    return this;
  }

  /**
   * Parse the training job ID from the active training text.
   * Expected format: "Active training: {id} ({status})"
   */
  async getActiveJobId(): Promise<string | null> {
    const text = await this.activeTrainingText.innerText().catch(() => '');
    const match = text.match(/Active training:\s*(\S+)/);
    return match ? match[1] : null;
  }
}
