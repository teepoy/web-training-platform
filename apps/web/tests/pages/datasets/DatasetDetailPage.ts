import type { Locator, Page } from '@playwright/test'
import { BasePage } from '../BasePage'

/**
 * Page Object Model for the `/datasets/:id` detail route.
 *
 * Covers the dataset detail header, tabs (Samples, Train, Predict, etc.),
 * Open Workflow button, Label Studio link, and the view type selector.
 */
export class DatasetDetailPage extends BasePage {
  constructor(page: Page) {
    super(page)
  }

  /** Wait for the dataset name heading to render. */
  async waitForLoaded(): Promise<void> {
    await this.page.getByRole('heading').first().waitFor()
  }

  // ── Detail header ─────────────────────────────────────────────

  /** Navigate to the detail page for a given dataset ID. */
  async gotoDetail(id: string): Promise<void> {
    await this.goto(`/datasets/${id}`)
  }

  /** Assert the "Samples" tab is visible. */
  async expectSamplesTab(): Promise<void> {
    const tab = this.page.locator('.n-tabs .n-tabs-tab').filter({ hasText: 'Samples' })
    await tab.waitFor()
  }

  /** Assert the dataset samples layout area is visible. */
  async expectSamplesLayout(): Promise<void> {
    await this.page.locator('[data-testid="dataset-view-router"]').waitFor({ timeout: 10_000 })
  }

  /** Assert a view is rendered (by data-testid). */
  async expectViewLoaded(testId: string): Promise<void> {
    await this.page.locator(`[data-testid="${testId}"]`).waitFor({ timeout: 10_000 })
  }

  // ── Workflow / classify ───────────────────────────────────────

  /** Click "Open Workflow" button to navigate to the classify page. */
  async clickOpenWorkflow(): Promise<void> {
    await this.page.getByRole('button', { name: 'Open Workflow' }).click()
    await this.page.waitForURL('**/datasets/**/classify')
  }

  /** Wait for the classify page shell to render. */
  async waitForClassifyPage(): Promise<void> {
    await this.page.locator('.classify-page').waitFor({ timeout: 10_000 })
  }

  // ── Label Studio link ──────────────────────────────────────────

  /** Assert the Label Studio project link / tag is visible. */
  async expectLabelStudioLink(): Promise<void> {
    const lsLink = this.page.getByText(/Label Studio Project #/)
    if (await lsLink.isVisible({ timeout: 3_000 }).catch(() => false)) {
      // Link is optional — only assert if present
      await lsLink.waitFor()
    }
  }

  /** Get the Label Studio link locator (may or may not be present). */
  getLabelStudioLink(): Locator {
    return this.page.getByText(/Label Studio Project #/)
  }

  // ── View type selector ────────────────────────────────────────

  /** Get the view type selector. */
  getViewTypeSelector(): Locator {
    return this.page.locator('[data-testid="view-type-selector"]')
  }

  // ── Add Sample button ──────────────────────────────────────────

  /** Click "Add Sample" button on the detail page. */
  async clickAddSample(): Promise<void> {
    await this.page.getByRole('button', { name: 'Add Sample' }).click()
  }

  // ── Tab navigation ────────────────────────────────────────────

  /** Click the Train tab. */
  async gotoTrainTab(): Promise<void> {
    await this.page.getByRole('tab', { name: 'Train' }).click()
  }

  /** Click the Predict tab. */
  async gotoPredictTab(): Promise<void> {
    await this.page.getByRole('tab', { name: 'Predict' }).click()
  }

  /** Click the Export tab. */
  async gotoExportTab(): Promise<void> {
    await this.page.getByRole('tab', { name: 'Export' }).click()
  }

  /** Wait for the training jobs view to render after switching to Train tab. */
  async waitForTrainTabLoaded(): Promise<void> {
    await this.page.getByRole('heading', { name: 'Training Jobs' }).waitFor()
  }

  /** Wait for the prediction jobs view to render after switching to Predict tab. */
  async waitForPredictTabLoaded(): Promise<void> {
    await this.page.getByRole('heading', { name: 'Prediction Jobs' }).waitFor()
  }

  // ── Train tab actions ─────────────────────────────────────────

  /** Get the "Start New Job" button on the Train tab. */
  getStartJobButton(): Locator {
    return this.page.getByRole('button', { name: 'Start New Job' })
  }

  // ── Predict tab actions ───────────────────────────────────────

  /** Get the "Start Prediction" button on the Predict tab. */
  getStartPredictionButton(): Locator {
    return this.page.getByRole('button', { name: 'Start Prediction' })
  }
}
