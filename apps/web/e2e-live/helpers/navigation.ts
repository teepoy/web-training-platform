import type { Page } from '@playwright/test'

/** Default timeout (ms) for page load / element visibility waits. */
const DEFAULT_WAIT_TIMEOUT = 10000

/** Polling interval (ms) between job status checks. */
const JOB_POLL_INTERVAL = 3000

/** Maximum time (ms) to wait for a job to reach a terminal state. */
const JOB_POLL_TIMEOUT = 60000

/**
 * Navigate to /datasets and wait for the Naive UI data table to render.
 */
export async function goToDatasets(page: Page): Promise<void> {
  await page.goto('/datasets')
  await page.waitForSelector('.n-data-table', { timeout: DEFAULT_WAIT_TIMEOUT })
}

/**
 * Navigate to dataset detail by clicking on a dataset name in the list.
 * Assumes the browser is already on /datasets.
 */
export async function goToDatasetDetail(
  page: Page,
  datasetName: string,
): Promise<void> {
  await page.getByText(datasetName, { exact: true }).first().click()
  await page.waitForURL('**/datasets/**')
}

/**
 * Navigate to /jobs and wait for the Naive UI data table to render.
 */
export async function goToJobs(page: Page): Promise<void> {
  await page.goto('/jobs')
  await page.waitForSelector('.n-data-table', { timeout: DEFAULT_WAIT_TIMEOUT })
}

/**
 * Navigate to /dashboard and wait for network idle.
 */
export async function goToDashboard(page: Page): Promise<void> {
  await page.goto('/dashboard')
  await page.waitForLoadState('networkidle')
}

/**
 * Navigate to /schedules and wait for network idle.
 */
export async function goToSchedules(page: Page): Promise<void> {
  await page.goto('/schedules')
  await page.waitForLoadState('networkidle')
}

/**
 * Navigate to /presets and wait for network idle.
 */
export async function goToPresets(page: Page): Promise<void> {
  await page.goto('/presets')
  await page.waitForLoadState('networkidle')
}

/**
 * Poll the /jobs page until a job matching `jobName` reaches a terminal state.
 *
 * Reloads the page every {@link JOB_POLL_INTERVAL} ms to fetch fresh server data.
 * Returns `"completed"`, `"failed"`, or throws if the timeout is exceeded.
 *
 * @param page - Playwright Page
 * @param jobName - Display name of the job (searched within table row text)
 * @param timeout - Maximum wait time in ms (default: {@link JOB_POLL_TIMEOUT})
 * @returns The terminal status string (`"completed"` or `"failed"`)
 */
export async function waitForJobComplete(
  page: Page,
  jobName: string,
  timeout: number = JOB_POLL_TIMEOUT,
): Promise<'completed' | 'failed'> {
  const startTime = Date.now()

  while (Date.now() - startTime < timeout) {
    await page.reload()
    await page.waitForSelector('.n-data-table', { timeout: DEFAULT_WAIT_TIMEOUT })

    const row = page.locator('.n-data-table tr', {
      has: page.getByText(jobName),
    })

    if ((await row.count()) > 0) {
      const rowText = (await row.first().innerText()).toLowerCase()

      if (rowText.includes('completed')) {
        return 'completed'
      }
      if (rowText.includes('failed')) {
        return 'failed'
      }
    }

    await page.waitForTimeout(JOB_POLL_INTERVAL)
  }

  throw new Error(`Job "${jobName}" did not complete within ${timeout}ms`)
}

/**
 * Wait for a Naive UI message toast to appear.
 *
 * Naive UI messages are rendered by `<n-message-provider>` with class
 * `.n-message`. When `text` is provided, the function waits for a toast
 * containing that substring.
 *
 * @param page - Playwright Page
 * @param text - Optional text to match within the toast content
 */
export async function waitForToast(page: Page, text?: string): Promise<void> {
  const locator = text
    ? page.locator('.n-message', { hasText: text })
    : page.locator('.n-message').first()

  await locator.waitFor({ timeout: DEFAULT_WAIT_TIMEOUT })
}
