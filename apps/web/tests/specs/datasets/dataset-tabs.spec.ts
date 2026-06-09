import { test, expect } from '../../fixtures'
import { DatasetDetailPage } from '../../pages/datasets/DatasetDetailPage'
import { makeTrainingJob } from '../../mocks/factories'

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

  const trainingJobSelect = authedPage.getByPlaceholder(
    'Select a completed training job',
  )
  await expect(trainingJobSelect).toBeVisible()
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
