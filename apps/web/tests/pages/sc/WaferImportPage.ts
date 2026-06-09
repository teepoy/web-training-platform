import type { Locator, Page } from '@playwright/test';
import { BasePage } from '../BasePage';

/**
 * Page Object Model for the SC import workflow.
 *
 * Covers:
 * - `/sc/preview` — SC preview page with search bar and inspection table
 * - Inspection tab (opened by clicking a table row)
 * - Import modal ("Import from SC Upstream")
 * - Form fields and "Start Import" button
 * - Redirect to `/datasets/:id/classify` on completion
 */
export class WaferImportPage extends BasePage {
  constructor(page: Page) {
    super(page);
  }

  async waitForLoaded(): Promise<void> {
    await this.page.locator('.sc-preview').waitFor({ timeout: 10_000 });
  }

  // ── Navigation ──────────────────────────────────────────────────

  async goToScPreview(): Promise<this> {
    await this.goto('/sc/preview');
    await this.waitForLoaded();
    return this;
  }

  // ── Search bar ──────────────────────────────────────────────────

  get startTimePicker(): Locator {
    return this.page.getByPlaceholder('Start Time');
  }

  get endTimePicker(): Locator {
    return this.page.getByPlaceholder('End Time');
  }

  get searchButton(): Locator {
    return this.page.getByRole('button', { name: 'Search' });
  }

  async fillTimeRange(startTime: string, endTime: string): Promise<this> {
    await this.startTimePicker.fill(startTime);
    await this.endTimePicker.fill(endTime);
    return this;
  }

  async clickSearch(): Promise<this> {
    await this.searchButton.click();
    return this;
  }

  // ── Inspection table ────────────────────────────────────────────

  get dataTable(): Locator {
    return this.page.locator('.n-data-table');
  }

  get firstRow(): Locator {
    return this.page.locator('.n-data-table tbody tr').first();
  }

  async waitForTableRows(): Promise<this> {
    await this.dataTable.waitFor({ timeout: 15_000 });
    await this.firstRow.waitFor({ timeout: 15_000 });
    return this;
  }

  async openFirstInspection(): Promise<this> {
    await this.firstRow.click();
    await this.inspectionTab.waitFor({ timeout: 10_000 });
    return this;
  }

  // ── Inspection tab ──────────────────────────────────────────────

  get inspectionTab(): Locator {
    return this.page.locator('.sc-preview-tab.active');
  }

  get importAsDatasetButton(): Locator {
    return this.page.getByRole('button', { name: 'Import as Dataset' });
  }

  async clickImportAsDataset(): Promise<this> {
    await this.importAsDatasetButton.click();
    return this;
  }

  // ── Import modal ────────────────────────────────────────────────

  get importModal(): Locator {
    return this.page
      .locator('.n-modal')
      .filter({ hasText: 'Import from SC Upstream' });
  }

  get datasetNameInput(): Locator {
    return this.page.getByPlaceholder('My SC Dataset');
  }

  get storageModeSelect(): Locator {
    return this.importModal.locator('.n-base-selection').first();
  }

  get startImportButton(): Locator {
    return this.page.getByRole('button', { name: 'Start Import' });
  }

  async waitForImportModal(): Promise<this> {
    await this.importModal.waitFor({ timeout: 5_000 });
    return this;
  }

  async fillDatasetName(name: string): Promise<this> {
    const input = this.datasetNameInput;
    await input.fill('');
    await input.fill(name);
    return this;
  }

  async selectStorageModeSparseShard(): Promise<this> {
    await this.storageModeSelect.click();
    await this.page
      .locator('.n-base-select-option')
      .filter({ hasText: 'Sparse Shard' })
      .click();
    return this;
  }

  async clickStartImport(): Promise<this> {
    await this.startImportButton.click();
    return this;
  }

  // ── Completion ──────────────────────────────────────────────────

  /**
   * Wait for the import to complete and the page to redirect to
   * `/datasets/:id/classify`. Returns the classify page URL.
   */
  async waitForImportCompletion(timeoutMs = 180_000): Promise<string> {
    await this.page.waitForURL('**/datasets/**/classify', { timeout: timeoutMs });
    return this.page.url();
  }

  /**
   * Extract the dataset ID from a `/datasets/:id/classify` URL.
   */
  extractDatasetId(url: string): string | null {
    return url.match(/\/datasets\/([^/]+)\/classify/)?.[1] ?? null;
  }
}
