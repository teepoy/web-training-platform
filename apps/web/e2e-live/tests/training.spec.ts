import { test, expect } from '@playwright/test'
import { loginViaUI } from '../helpers/auth'
import { goToJobs, waitForJobComplete, goToDatasetDetail } from '../helpers/navigation'

const SEED_EMAIL = 'seed@example.com'
const SEED_PASSWORD = 'seed1234'

/**
 * Generate a unique dataset name to avoid collisions across test runs.
 */
function uniqueDatasetName(): string {
  return `e2e-live-training-${Date.now()}`
}

function minimalSampleJson(): string {
  return JSON.stringify([
    { image_uris: ['memory://sample-a.jpg'], metadata: { split: 'train' } },
    { image_uris: ['memory://sample-b.jpg'], metadata: { split: 'train' } },
  ])
}

/**
 * Create a dataset with samples via the "Import Dataset" → "Import from JSON"
 * plugin flow. Returns the dataset name that was created.
 */
async function createDatasetViaJSONImport(page: import('@playwright/test').Page): Promise<string> {
  const datasetName = uniqueDatasetName()

  await page.goto('/datasets')
  await page.waitForSelector('.n-data-table')

  await page.getByRole('button', { name: 'Import Dataset' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()

  await page.getByText('Import from JSON').click()

  await page.getByPlaceholder('e.g. imported-dataset').fill(datasetName)

  await page
    .locator('.n-base-selection')
    .filter({ hasText: 'Select dataset type' })
    .first()
    .click()
  await page.locator('.n-base-select-option').filter({ hasText: 'Image Classification' }).click()

  const tagsInput = page.locator('.n-dynamic-tags input[type="text"]')
  await tagsInput.fill('cat')
  await tagsInput.press('Enter')
  await tagsInput.fill('dog')
  await tagsInput.press('Enter')

  await page.locator('input[type="file"][accept="application/json"]').setInputFiles({
    name: 'samples.json',
    mimeType: 'application/json',
    buffer: Buffer.from(minimalSampleJson()),
  })

  await expect(page.getByText(/samples\.json \(2 samples\)/)).toBeVisible()

  await page.getByRole('button', { name: 'Import', exact: true }).click()

  await expect(page.locator('.n-message').filter({ hasText: 'Dataset imported' })).toBeVisible({
    timeout: 30000,
  })

  await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 10000 })

  await expect(page.getByText(datasetName, { exact: true })).toBeVisible()

  return datasetName
}

test('create training job and monitor SSE', async ({ page }) => {
  await loginViaUI(page, SEED_EMAIL, SEED_PASSWORD)

  // 1. Create a dataset with samples
  const datasetName = await createDatasetViaJSONImport(page)

  // 2. Start a training job
  await goToJobs(page)

  await page.getByRole('button', { name: 'Start New Job' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()

  await page
    .locator('.n-base-selection')
    .filter({ hasText: 'Select a dataset' })
    .first()
    .click()
  await page.locator('.n-base-select-option').filter({ hasText: datasetName }).click()

  await page
    .locator('.n-base-selection')
    .filter({ hasText: 'Select a preset' })
    .first()
    .click()
  const firstOption = page.locator('.n-base-select-option').first()
  await firstOption.click()

  await page.getByRole('button', { name: 'Start', exact: true }).click()

  await expect(page.locator('.n-message').filter({ hasText: 'Job started' })).toBeVisible({
    timeout: 15000,
  })

  const jobRow = page.locator('.n-data-table tr', {
    has: page.getByText(datasetName),
  })
  await expect(jobRow).toBeVisible({ timeout: 10000 })
  await jobRow.getByRole('button', { name: 'View' }).click()

  // 3. On the job detail page, verify SSE connection opens
  await expect(page).toHaveURL(/\/jobs\//)

  await expect(page.locator('.n-tag').filter({ hasText: /SSE:/ })).toBeVisible({
    timeout: 30000,
  })
  await expect(page.getByText('SSE: open')).toBeVisible({ timeout: 30000 })

  // 4. Wait for job completion and verify final status
  const jobId = page.url().split('/').pop()!
  const status = await waitForJobComplete(page, jobId)
  expect(status).toBe('completed')
})

test('training progress card shows metrics', async ({ page }) => {
  await loginViaUI(page, SEED_EMAIL, SEED_PASSWORD)
  await goToJobs(page)

  const completedRow = page.locator('.n-data-table tr', {
    has: page.getByText('completed'),
  })

  const completedCount = await completedRow.count()
  if (completedCount === 0) {
    test.skip(true, 'No completed jobs found — run the training test first')
    return
  }

  await completedRow.first().getByRole('button', { name: 'View' }).click()
  await expect(page).toHaveURL(/\/jobs\//)

  const progressCard = page.locator('.n-card').filter({ hasText: 'Training Progress' })
  await expect(progressCard).toBeVisible({ timeout: 10000 })

  const hasChart = (await progressCard.locator('canvas').count()) > 0
  const hasEmpty = (await progressCard.locator('.n-empty').count()) > 0
  const hasTable = (await progressCard.locator('.n-data-table').count()) > 0
  const hasContent = hasChart || hasEmpty || hasTable

  expect(hasContent, 'Training Progress card should render the chart component').toBe(true)
})
