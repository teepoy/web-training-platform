import type { Locator, Page } from '@playwright/test'
import { BasePage } from '../BasePage'

/**
 * Page Object Model for the `/datasets` list route.
 *
 * Covers the dataset toolbar (Import Dataset, Preview Dataset buttons)
 * and row-level actions (View, Make Public/Make Private, Delete)
 * rendered by the {@link DatasetToolbar} and {@link DatasetTable}
 * + {@link DatasetRowActions} components.
 */
export class DatasetListPage extends BasePage {
  constructor(page: Page) {
    super(page)
  }

  /** Wait for the Naive UI data table to render, signalling the list is ready. */
  async waitForLoaded(): Promise<void> {
    await this.page.waitForSelector('.n-data-table')
  }

  // ── Toolbar buttons ────────────────────────────────────────────

  /** Click the "Import Dataset" toolbar button and wait for the FlowModal dialog. */
  async clickImportDataset(): Promise<void> {
    await this.page.getByRole('button', { name: 'Import Dataset' }).click()
    await this.page.getByRole('dialog').waitFor()
  }

  /** Click the "Preview Dataset" toolbar button and wait for the FlowModal dialog. */
  async clickPreviewDataset(): Promise<void> {
    await this.page.getByRole('button', { name: 'Preview Dataset' }).click()
    await this.page.getByRole('dialog').waitFor()
  }

  // ── FlowModal card selectors ───────────────────────────────────

  /** Assert the Import Dataset flow modal is open with expected card labels. */
  async expectImportFlowModal(): Promise<void> {
    const dialog = this.page.getByRole('dialog')
    // "Manual Sample Entry" and "Import from JSON" are cards shown inside FlowModal
    await dialog.waitFor()
  }

  /** Assert the Preview Dataset flow modal is open with expected card labels. */
  async expectPreviewFlowModal(): Promise<void> {
    const dialog = this.page.getByRole('dialog')
    await dialog.waitFor()
  }

  /**
   * Get a locator for a specific flow card inside the currently open FlowModal.
   */
  expectFlowCard(label: string): Locator {
    return this.page.getByRole('dialog').getByText(label)
  }

  // ── Dataset row helpers ────────────────────────────────────────

  /**
   * Assert a dataset by name is visible in the table.
   */
  async expectDatasetVisible(name: string): Promise<void> {
    await this.page.getByText(name).waitFor()
  }

  /**
   * Click the "View" button on a dataset row. Navigates to the detail page.
   */
  async clickView(): Promise<void> {
    await this.page.getByRole('button', { name: 'View', exact: true }).click()
  }

  /**
   * Click "Make Public" button on a dataset row (only visible for superadmins
   * on own-org datasets).
   */
  async clickMakePublic(): Promise<void> {
    await this.page.getByRole('button', { name: 'Make Public' }).click()
  }

  /**
   * Click "Make Private" button on a dataset row.
   */
  async clickMakePrivate(): Promise<void> {
    await this.page.getByRole('button', { name: 'Make Private' }).click()
  }

  /**
   * Click "Delete" button on a dataset row (only visible for superadmins
   * on own-org datasets).
   */
  async clickDelete(): Promise<void> {
    await this.page.getByRole('button', { name: 'Delete' }).click()
  }

  /**
   * Assert the "Make Public" button is visible (superadmin + own-org check).
   */
  async expectMakePublicVisible(): Promise<void> {
    await this.page.getByRole('button', { name: 'Make Public' }).waitFor()
  }

  /**
   * Assert the "Delete" button is visible (superadmin + own-org check).
   */
  async expectDeleteVisible(): Promise<void> {
    await this.page.getByRole('button', { name: 'Delete' }).waitFor()
  }

  /**
   * Assert the URL matches the datasets detail pattern after clicking View.
   */
  async expectNavigatedToDetail(): Promise<void> {
    await this.page.waitForURL('**/datasets/**')
  }

  // ── Table row click ────────────────────────────────────────────

  /** Click a dataset row by its display name. */
  async clickRow(name: string): Promise<void> {
    await this.page.getByText(name, { exact: true }).first().click()
  }
}
