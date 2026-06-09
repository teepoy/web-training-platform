import type { Page } from '@playwright/test'
import { ClassifyWorkflowPage } from './ClassifyWorkflowPage'

/**
 * Page Object Model focused on wafer-map interactions within the
 * classify page at `/datasets/:id/classify`.
 *
 * Extends {@link ClassifyWorkflowPage} and exposes wafer-map-specific
 * selectors and actions (panel, canvas, chart wrap, zoom, footer).
 */
export class WaferMapPage extends ClassifyWorkflowPage {
  constructor(page: Page) {
    super(page)
  }

  async waitForLoaded(): Promise<void> {
    await this.getWaferMapPanel().waitFor()
  }
}
