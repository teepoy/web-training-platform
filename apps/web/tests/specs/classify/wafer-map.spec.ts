import { test, expect } from '../../fixtures'
import { makeSample } from '../../mocks/factories'
import { WaferMapPage } from '../../pages/classify/WaferMapPage'

const datasetId = 'dataset-wafer-1'

const waferSamples = [
  makeSample(datasetId, 0, {
    id: 'sample-w1',
    metadata: { split: 'val', wafer_x: 0.1, wafer_y: 0.2 },
  }),
  makeSample(datasetId, 1, {
    id: 'sample-w2',
    metadata: { split: 'val', wafer_x: -0.3, wafer_y: 0.5 },
  }),
  makeSample(datasetId, 2, {
    id: 'sample-w3',
    metadata: { split: 'val', wafer_x: 0.7, wafer_y: -0.4 },
  }),
]

test('wafer-map panel renders with dieGrid config @mock', async ({
  authedPage,
  apiMocks,
}) => {
  const page = new WaferMapPage(authedPage)

  await apiMocks.datasets.mockGetDataset(datasetId, {
    name: 'wafer-dataset',
    ls_project_id: '100',
    ls_project_url: 'http://localhost:8080/projects/100',
  })
  await apiMocks.datasets.mockListSamples(datasetId, waferSamples)
  await apiMocks.datasets.mockAnnotationStats(datasetId, {
    total_samples: 3,
    annotated_samples: 0,
    unlabeled_samples: 3,
  })
  await apiMocks.datasets.mockDatasetQuery(datasetId)

  await apiMocks.prediction.mockListModels([])
  await apiMocks.prediction.mockListPredictionJobs([])
  await apiMocks.training.mockListTrainingJobs([])
  await apiMocks.training.mockListTrainers([])

  const pageErrors: string[] = []
  authedPage.on('pageerror', (error) => pageErrors.push(error.message))

  await page.goto(`/datasets/${datasetId}/classify`)
  await page.waitForLoaded()

  await expect(page.getWaferMapPanel()).toBeVisible()
  await expect(page.getWaferMapCanvas()).toBeVisible()
  await expect(page.getWaferMapPanel()).not.toContainText('No wafer points')
  await expect(page.getChartWrap()).toBeVisible()

  expect(pageErrors).toHaveLength(0)
  await expect(page.getWaferMapFooter()).toContainText('3 points')
})

test('wafer-map zoom + Reset Zoom button @mock', async ({
  authedPage,
  apiMocks,
}) => {
  const page = new WaferMapPage(authedPage)

  await apiMocks.datasets.mockGetDataset(datasetId, {
    name: 'wafer-dataset',
    ls_project_id: '100',
    ls_project_url: 'http://localhost:8080/projects/100',
  })
  await apiMocks.datasets.mockListSamples(datasetId, waferSamples)
  await apiMocks.datasets.mockAnnotationStats(datasetId, {
    total_samples: 3,
    annotated_samples: 0,
    unlabeled_samples: 3,
  })
  await apiMocks.datasets.mockDatasetQuery(datasetId)

  await apiMocks.prediction.mockListModels([])
  await apiMocks.prediction.mockListPredictionJobs([])
  await apiMocks.training.mockListTrainingJobs([])
  await apiMocks.training.mockListTrainers([])

  const pageErrors: string[] = []
  authedPage.on('pageerror', (error) => pageErrors.push(error.message))

  await page.goto(`/datasets/${datasetId}/classify`)
  await page.waitForLoaded()

  await expect(page.getWaferMapPanel()).toBeVisible()
  await expect(page.getWaferMapCanvas()).toBeVisible()

  await expect(page.getResetZoomButton()).not.toBeVisible()

  const chartWrap = page.getChartWrap()
  const box = await chartWrap.boundingBox()
  expect(box).not.toBeNull()

  await page.simulateZoom()

  await authedPage.evaluate(
    () => new Promise((resolve) => requestAnimationFrame(resolve)),
  )
  await authedPage.evaluate(
    () => new Promise((resolve) => requestAnimationFrame(resolve)),
  )

  await expect(page.getResetZoomButton()).toBeVisible({ timeout: 10000 })

  await page.clickResetZoom()
  await expect(page.getResetZoomButton()).not.toBeVisible()

  expect(pageErrors).toHaveLength(0)
})
