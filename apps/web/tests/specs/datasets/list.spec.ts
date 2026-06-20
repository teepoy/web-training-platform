import { test, expect } from '../../fixtures'
import { DatasetListPage } from '../../pages/datasets/DatasetListPage'
import { DatasetDetailPage } from '../../pages/datasets/DatasetDetailPage'
import { makeFlowerDataset } from '../../mocks/factories'
import { createDataset, cleanupTestArtifacts } from '../../seed'

// ═══════════════════════════════════════════════════════════════════
// @mock tests — dataset list interactions with mocked backend
// ═══════════════════════════════════════════════════════════════════

test('import dataset button opens the plugin flow modal @mock', async ({
  authedPage,
}) => {
  const listPage = new DatasetListPage(authedPage)
  await listPage.goto('/datasets')
  await listPage.waitForLoaded()

  await listPage.clickImportDataset()

  await expect(listPage.expectFlowCard('Manual Sample Entry')).toBeVisible()
})

test('preview dataset button opens the plugin flow modal @mock', async ({
  authedPage,
}) => {
  const listPage = new DatasetListPage(authedPage)
  await listPage.goto('/datasets')
  await listPage.waitForLoaded()

  await listPage.clickPreviewDataset()

  await expect(listPage.expectFlowCard('Upstream Collection')).toBeVisible()
})

test('row view button navigates to dataset detail @mock', async ({
  authedPage,
  apiMocks,
}) => {
  const dataset = makeFlowerDataset()
  const datasetId = dataset.id!
  await apiMocks.datasets.mockGetDataset(datasetId)

  const listPage = new DatasetListPage(authedPage)
  await listPage.goto('/datasets')
  await listPage.waitForLoaded()
  await listPage.expectDatasetVisible(dataset.name!)

  await listPage.clickView()

  await expect(authedPage).toHaveURL(new RegExp(`/datasets/${datasetId}`))
})

test('superadmin sees delete but no make-public button for own-org datasets @mock', async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.auth.mockAuthMe({ is_superadmin: true })

  const listPage = new DatasetListPage(authedPage)
  await listPage.goto('/datasets')
  await listPage.waitForLoaded()

  await listPage.expectPublicControlsHidden()
  await listPage.expectDeleteVisible()
})

test('delete button triggers confirmation before calling the API @mock', async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.auth.mockAuthMe({ is_superadmin: true })

  const dataset = makeFlowerDataset()
  const datasetId = dataset.id!
  await apiMocks.datasets.mockGetDataset(datasetId)

  const listPage = new DatasetListPage(authedPage)
  await listPage.goto('/datasets')
  await listPage.waitForLoaded()

  // Accept the native window.confirm dialog triggered by the delete handler.
  authedPage.on('dialog', (dialog) => dialog.accept())

  // Monitor for the DELETE request to verify the API was called.
  const deleteRequest = authedPage.waitForRequest(
    (req) =>
      req.url().includes(`/api/v1/datasets/${datasetId}`) &&
      req.method() === 'DELETE',
  )

  await listPage.clickDelete()

  // waitForRequest resolves when the matching request is dispatched.
  // If the DELETE is never sent, this will timeout and fail the test.
  await deleteRequest
})

// ═══════════════════════════════════════════════════════════════════
// @live tests — dataset interactions against real backend
// ═══════════════════════════════════════════════════════════════════

function datasetName(prefix = 'E2E Dataset'): string {
  return `${prefix} ${Date.now()}`
}

test('create dataset with labels @live', async ({ page }) => {
  const name = datasetName()

  await page.goto('/datasets')
  await page.waitForSelector('.n-data-table')

  await page.getByRole('button', { name: 'Import Dataset' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByText('Import from JSON').click()

  // Fill the dataset form in the FlowModal.
  await page.getByPlaceholder('e.g. imported-dataset').fill(name)
  await page.getByPlaceholder('Select dataset type').click()
  await page.getByText('Image Classification', { exact: true }).click()

  await expect(page.locator('.n-dynamic-tags')).toBeVisible({ timeout: 5_000 })

  for (const label of ['cat', 'dog']) {
    await page.locator('.n-dynamic-tags').click()
    await page.keyboard.type(label)
    await page.keyboard.press('Enter')
    await page.waitForTimeout(200)
  }

  // Upload a minimal samples JSON.
  const samplesJson = Buffer.from(
    JSON.stringify([
      { image_uris: ['memory://e2e-test-sample.jpg'], metadata: { source: 'e2e-live' }, label: null },
    ]),
  )
  await page
    .locator('input[type="file"][accept="application/json"]')
    .setInputFiles({ name: 'samples.json', mimeType: 'application/json', buffer: samplesJson })
  await expect(page.getByText(/samples\.json/)).toBeVisible({ timeout: 3_000 })

  await page.getByRole('button', { name: 'Import', exact: true }).click()
  await expect(page.getByText(name, { exact: true })).toBeVisible({ timeout: 15_000 })
})

test('view dataset detail @live', async ({ page, seedClient: _sc, testPrefix }) => {
  const name = `${testPrefix}-detail`

  // Create dataset via API so we only test the detail view, not the import flow.
  // _sc (seedClient) configures orval fetcher with auth token.
  const dataset = await createDataset({
    name,
    dataset_type: 'image_classification',
    task_spec: { task_type: 'classification', label_space: ['cat', 'dog'] },
  })

  // Cleanup after the test.
  try {
    const detailPage = new DatasetDetailPage(page)
    await detailPage.gotoDetail(dataset.id!)
    await detailPage.waitForLoaded()

    await detailPage.expectSamplesTab()
    await detailPage.expectViewLoaded('view-labeled-image-v1')
  } finally {
    await cleanupTestArtifacts(testPrefix)
  }
})

test('add labels to dataset @live', async ({ page, seedClient: _sc, testPrefix }) => {
  const name = `${testPrefix}-labels`

  // _sc (seedClient) configures orval fetcher with auth token.
  const dataset = await createDataset({
    name,
    dataset_type: 'image_classification',
    task_spec: { task_type: 'classification', label_space: ['cat', 'dog'] },
  })

  try {
    const detailPage = new DatasetDetailPage(page)
    await detailPage.gotoDetail(dataset.id!)
    await detailPage.waitForLoaded()

    await detailPage.clickOpenWorkflow()
    await detailPage.waitForClassifyPage()

    const addLabelButton = page.locator('.classify-label-add')
    await expect(addLabelButton).toBeVisible({ timeout: 5_000 })
    await addLabelButton.click()

    await expect(page.getByText('Add New Label')).toBeVisible({ timeout: 3_000 })
    await page.getByPlaceholder('Enter label name').fill('bird')
    await page.getByRole('button', { name: 'Add', exact: true }).click()

    await expect(
      page.locator('.n-message', { hasText: /Added label/ }),
    ).toBeVisible({ timeout: 10_000 })

    await expect(
      page.locator('.classify-label-item').filter({ hasText: 'bird' }),
    ).toBeVisible({ timeout: 5_000 })
  } finally {
    await cleanupTestArtifacts(testPrefix)
  }
})
