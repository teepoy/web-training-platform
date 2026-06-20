import { test, expect } from '../../fixtures'
import { DatasetDetailPage } from '../../pages/datasets/DatasetDetailPage'
import { makePredictionJob, makeTrainingJob } from '../../mocks/factories'

const datasetId = 'dataset-tabs-1'

test('Train tab disables Start New Job button when allowTrain=false @mock', async ({
  authedPage,
  apiMocks,
}) => {
  const page = new DatasetDetailPage(authedPage)

  await apiMocks.datasets.mockGetDataset(datasetId, {
    task_spec: { task_type: 'classification', label_space: ['rose', 'tulip'] },
  })
  await apiMocks.datasets.mockDatasetStatus(datasetId, {
    allow_train: false,
    annotated_samples: 0,
    total_samples: 10,
  })
  await apiMocks.training.mockListTrainingJobs([])
  await apiMocks.training.mockListTrainers([])

  await page.gotoDetail(datasetId)
  await page.waitForLoaded()

  await page.gotoTrainTab()
  await page.waitForTrainTabLoaded()

  const startButton = page.getStartJobButton()
  await expect(startButton).toBeVisible()
  await expect(startButton).toBeDisabled()
})

test('Train tab enables Start New Job button when allowTrain=true @mock', async ({
  authedPage,
  apiMocks,
}) => {
  const page = new DatasetDetailPage(authedPage)

  await apiMocks.datasets.mockGetDataset(datasetId, {
    task_spec: { task_type: 'classification', label_space: ['rose', 'tulip'] },
  })
  await apiMocks.datasets.mockDatasetStatus(datasetId, {
    allow_train: true,
    annotated_samples: 5,
    total_samples: 10,
  })
  await apiMocks.training.mockListTrainingJobs([])
  await apiMocks.training.mockListTrainers([])

  await page.gotoDetail(datasetId)
  await page.waitForLoaded()

  await page.gotoTrainTab()
  await page.waitForTrainTabLoaded()

  const startButton = page.getStartJobButton()
  await expect(startButton).toBeVisible()
  await expect(startButton).toBeEnabled()
})

test('Predict tab shows Start Prediction button and opens modal with training job selector @mock', async ({
  authedPage,
  apiMocks,
}) => {
  const page = new DatasetDetailPage(authedPage)

  await apiMocks.datasets.mockGetDataset(datasetId, {
    task_spec: { task_type: 'classification', label_space: ['rose', 'tulip'] },
  })
  await apiMocks.datasets.mockDatasetStatus(datasetId)
  await apiMocks.prediction.mockListPredictionJobs([])
  await apiMocks.training.mockListTrainingJobs([
    makeTrainingJob({
      id: 'job-completed-1',
      dataset_id: datasetId,
      status: 'completed',
    }),
  ])

  await page.gotoDetail(datasetId)
  await page.waitForLoaded()

  await page.gotoPredictTab()
  await page.waitForPredictTabLoaded()

  const startButton = page.getStartPredictionButton()
  await expect(startButton).toBeVisible()

  await startButton.click()

  await expect(authedPage.getByRole('dialog')).toBeVisible()

  const dialog = authedPage.getByRole('dialog')
  await expect(dialog.getByText('Training Job', { exact: true })).toBeVisible()
  await expect(dialog.getByText('Select a completed training job')).toBeVisible()
})

test('Predict tab only shows prediction jobs for the current dataset @mock', async ({
  authedPage,
  apiMocks,
}) => {
  const page = new DatasetDetailPage(authedPage)

  await apiMocks.datasets.mockGetDataset(datasetId, {
    task_spec: { task_type: 'classification', label_space: ['rose', 'tulip'] },
  })
  await apiMocks.datasets.mockDatasetStatus(datasetId)
  await apiMocks.prediction.mockListPredictionJobs([
    makePredictionJob({
      id: 'current1-prediction-job',
      dataset_id: datasetId,
      status: 'completed',
    }),
    makePredictionJob({
      id: 'other999-prediction-job',
      dataset_id: 'other-dataset',
      status: 'completed',
    }),
  ])
  await apiMocks.training.mockListTrainingJobs([])

  await page.gotoDetail(datasetId)
  await page.waitForLoaded()

  await page.gotoPredictTab()
  await page.waitForPredictTabLoaded()

  await expect(authedPage.getByText('current1…')).toBeVisible()
  await expect(authedPage.getByText('other999…')).not.toBeVisible()
})

test('Task Explorer returns to the source route from query @mock', async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.datasets.mockGetDataset(datasetId, {
    task_spec: { task_type: 'classification', label_space: ['rose', 'tulip'] },
  })
  await apiMocks.datasets.mockDatasetStatus(datasetId)
  await authedPage.route('**/api/v1/task-tracker/tasks**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })

  await authedPage.goto(`/tasks?from=${encodeURIComponent(`/datasets/${datasetId}?tab=predict`)}`)
  await authedPage.getByTestId('task-explorer-back').click()

  await expect(authedPage).toHaveURL(new RegExp(`/datasets/${datasetId}`))
})

test('Train tab modal hides dataset selector when datasetId prop is set @mock', async ({
  authedPage,
  apiMocks,
}) => {
  const page = new DatasetDetailPage(authedPage)

  await apiMocks.datasets.mockGetDataset(datasetId, {
    task_spec: { task_type: 'classification', label_space: ['rose', 'tulip'] },
  })
  await apiMocks.datasets.mockDatasetStatus(datasetId, {
    allow_train: true,
    annotated_samples: 5,
    total_samples: 10,
  })
  await apiMocks.training.mockListTrainingJobs([])
  await apiMocks.training.mockListTrainers([])

  await page.gotoDetail(datasetId)
  await page.waitForLoaded()

  await page.gotoTrainTab()
  await page.waitForTrainTabLoaded()

  const startButton = page.getStartJobButton()
  await startButton.click()

  await expect(authedPage.getByRole('dialog')).toBeVisible()

  // Dataset selector should NOT be visible — it's auto-set from props.datasetId
  const datasetFormLabel = authedPage.getByText('Dataset', { exact: true })
  await expect(datasetFormLabel).not.toBeVisible()
})
