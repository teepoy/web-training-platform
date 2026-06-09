import { test, expect } from '../../fixtures'
import { makeSample } from '../../mocks/factories'
import { DatasetSamplesPage } from '../../pages/datasets/DatasetSamplesPage'
import { DatasetDetailPage } from '../../pages/datasets/DatasetDetailPage'
import { createDataset, addSamples, cleanupTestArtifacts } from '../../seed'

// ═══════════════════════════════════════════════════════════════════
// @mock tests — sample browser interactions with mocked backend
// ═══════════════════════════════════════════════════════════════════

const datasetId = 'dataset-ds-1'
const sampleId = 'sample-ds-1'

test('dataset Samples tab shows shared browser controls and opens Sample Detail @mock', async ({
  authedPage,
  apiMocks,
}) => {
  const page = new DatasetSamplesPage(authedPage)

  await apiMocks.datasets.mockGetDataset(datasetId, {
    ls_project_id: '101',
    ls_project_url: 'http://localhost:8080/projects/101',
  })
  await apiMocks.datasets.mockListSamples(datasetId, [
    makeSample(datasetId, 0, { id: sampleId, metadata: { split: 'train' } }),
    makeSample(datasetId, 1, { id: 'sample-ds-2', metadata: { split: 'val' } }),
  ])
  await apiMocks.datasets.mockAnnotationStats(datasetId, {
    total_samples: 2,
    annotated_samples: 0,
    unlabeled_samples: 2,
  })
  await apiMocks.datasets.mockGetSample(datasetId, sampleId, {
    metadata: { split: 'train' },
  })
  await apiMocks.datasets.mockSampleAnnotations(datasetId, sampleId)
  await apiMocks.datasets.mockSamplePredictions(datasetId, sampleId)
  await apiMocks.datasets.mockSampleSimilar(datasetId, sampleId)
  await apiMocks.datasets.mockDatasetQuery(datasetId)

  await apiMocks.training.mockListTrainingJobs([])
  await apiMocks.training.mockListTrainers([])

  await page.goto(`/datasets/${datasetId}`)
  await page.waitForLoaded()

  await expect(page.getGridRadio()).toBeVisible()
  await expect(page.getListRadio()).toBeVisible()
  await expect(page.getSidebarToggle()).toBeVisible()

  const itemCount = await page.getSampleBrowserItems().count()
  expect(itemCount).toBeGreaterThan(0)

  await page.clickFirstSample()
  await expect(page.getSampleDetail()).toBeVisible()

  await expect(page.getWaferMapPanel()).toBeVisible()
  await expect(page.getWaferMapCanvas()).toBeVisible()
  await expect(page.getWaferMapPanel()).not.toContainText('No wafer points')
})

// ═══════════════════════════════════════════════════════════════════
// @live tests — sample interactions against real backend
// ═══════════════════════════════════════════════════════════════════

test('create sample with image upload @live', async ({ page, liveAuth, seedClient: _sc, testPrefix }) => {
  await page.addInitScript((token) => {
    localStorage.setItem('auth_token', token)
  }, liveAuth.token)

  const datasetName = `${testPrefix}-samples-upload`

  const dataset = await createDataset({
    name: datasetName,
    dataset_type: 'image_classification',
    task_spec: { task_type: 'classification', label_space: ['cat', 'dog'] },
  })

  try {
    const detailPage = new DatasetDetailPage(page)
    await detailPage.gotoDetail(dataset.id!)
    await detailPage.waitForLoaded()

    await expect(page.getByRole('button', { name: 'Add Sample' })).toBeVisible()
    await page.getByRole('button', { name: 'Add Sample' }).click()

    await expect(page.getByText('Manual Sample Entry')).toBeVisible()
    await page.getByText('Manual Sample Entry').click()

    const fileInput = page.locator('input[type="file"]').first()
    await expect(fileInput).toBeAttached()

    const pngBytes = Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPj/HwADBwIAMCbHYQAAAABJRU5ErkJggg==',
      'base64',
    )
    await fileInput.setInputFiles({
      name: 'test-sample.png',
      mimeType: 'image/png',
      buffer: pngBytes,
    })

    await expect(page.locator('.n-image img').first()).toBeVisible({ timeout: 5_000 })

    await page.getByRole('button', { name: 'Create' }).click()

    await expect(page.locator('.n-message', { hasText: 'Sample created' })).toBeVisible({
      timeout: 10_000,
    })

    await expect(page.locator('[data-sb-item]').first()).toBeVisible({ timeout: 10_000 })
  } finally {
    await cleanupTestArtifacts(testPrefix)
  }
})

test('annotate sample with label @live', async ({ page, liveAuth, seedClient: _sc, testPrefix }) => {
  await page.addInitScript((token) => {
    localStorage.setItem('auth_token', token)
  }, liveAuth.token)

  const datasetName = `${testPrefix}-samples-annot`

  const dataset = await createDataset({
    name: datasetName,
    dataset_type: 'image_classification',
    task_spec: { task_type: 'classification', label_space: ['rose', 'tulip'] },
  })

  await addSamples(dataset.id!, {
    items: [
      { image_uris: ['memory://annot-test.png'], metadata: { source: 'e2e' } },
    ],
  })

  try {
    const detailPage = new DatasetDetailPage(page)
    await detailPage.gotoDetail(dataset.id!)
    await detailPage.waitForLoaded()

    await expect(page.locator('[data-sb-item]').first()).toBeVisible({ timeout: 10_000 })

    await page.locator('[data-sb-item]').first().click()
    await expect(page.getByText('Sample Detail')).toBeVisible({ timeout: 5_000 })

    const labelSelect = page.locator('.n-drawer .n-select').first()
    await labelSelect.click()

    const selectOption = page.locator('.n-base-select-option').filter({ hasText: 'rose' })
    await expect(selectOption).toBeVisible({ timeout: 5_000 })
    await selectOption.click()

    await page.locator('.n-drawer').getByRole('button', { name: 'Add' }).first().click()

    await expect(
      page.locator('.n-drawer .n-tag').filter({ hasText: 'rose' }).first(),
    ).toBeVisible({ timeout: 10_000 })

    await expect(
      page.locator('.n-drawer').getByRole('button', { name: 'Edit' }),
    ).toBeVisible({ timeout: 5_000 })
  } finally {
    await cleanupTestArtifacts(testPrefix)
  }
})
