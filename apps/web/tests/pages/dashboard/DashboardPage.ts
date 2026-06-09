import type { Locator, Page } from '@playwright/test'
import { BasePage } from '../BasePage'

/**
 * Page Object Model for the Dashboard at `/dashboard`.
 */
export class DashboardPage extends BasePage {
  constructor(page: Page) {
    super(page)
  }

  async waitForLoaded(): Promise<void> {
    await this.page.waitForLoadState('networkidle')
  }

  async goto(): Promise<void> {
    await this.page.goto('/dashboard')
    await this.waitForLoaded()
  }

  /** Locator for the "Work Pool" statistics card. */
  get workPoolCard(): Locator {
    return this.page.getByTestId('dashboard-work-pool-card')
  }

  /** Locator for the "Job Queue" statistics card. */
  get jobQueueCard(): Locator {
    return this.page.getByTestId('dashboard-job-queue-card')
  }

  /** Locator for the "Service Health" card. */
  get serviceHealthCard(): Locator {
    return this.page.getByTestId('dashboard-service-health-card')
  }

  /** Locator for the "Recent Jobs" card. */
  get recentJobsCard(): Locator {
    return this.page.getByTestId('dashboard-recent-jobs-card')
  }
}
