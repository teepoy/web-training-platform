import type { Locator, Page } from '@playwright/test';
import { BasePage } from '../BasePage';

/**
 * Page Object Model for the SC annotation phase on the classify page.
 *
 * Covers:
 * - `/datasets/:id/classify` — classify page with sample browser + sidebar
 * - Annotation grid and label selection in the sidebar
 */
export class WaferAnnotatePage extends BasePage {
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

  // ── Classify page ───────────────────────────────────────────────

  get classifyPage(): Locator {
    return this.page.locator('.classify-page');
  }

  get sampleBrowserItems(): Locator {
    return this.page.locator('[data-sb-item]');
  }

  get gridRadio(): Locator {
    return this.page.getByRole('radio', { name: 'Grid' });
  }

  get listRadio(): Locator {
    return this.page.getByRole('radio', { name: 'List' });
  }

  // ── Annotation ──────────────────────────────────────────────────

  get annotationGrid(): Locator {
    return this.page.locator('.annotation-grid');
  }

  /** Get a label button by text in the annotation sidebar. */
  getLabelButton(label: string): Locator {
    return this.page.locator('.annotation-grid__label').filter({ hasText: label });
  }

  async waitForSamples(): Promise<this> {
    await this.page.waitForSelector('[data-sb-item]', { timeout: 10_000 });
    return this;
  }
}
