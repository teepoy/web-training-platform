import { test, expect } from "../../fixtures";
import { makeModel, makeSample } from "../../mocks/factories";
import { ClassifyWorkflowPage } from "../../pages/classify/ClassifyWorkflowPage";

const datasetId = "dataset-review-1";
const modelId = "model-review-1";
const predictionJobId = "prediction-job-1";

const reviewPredictions = [
  {
    id: "prediction-review-1",
    sample_id: "sample-review-1",
    predicted_label: "rose",
    confidence: 0.91,
    model_id: modelId,
    target: "image_classification",
    model_version: null,
    job_id: predictionJobId,
    created_at: "2026-01-01T00:00:00Z",
    error: null,
  },
  {
    id: "prediction-review-2",
    sample_id: "sample-review-2",
    predicted_label: "tulip",
    confidence: 0.87,
    model_id: modelId,
    target: "image_classification",
    model_version: null,
    job_id: predictionJobId,
    created_at: "2026-01-01T00:00:00Z",
    error: null,
  },
];

test("runs prediction review flow from /datasets/:id/classify @legacy", async ({
  authedPage,
  apiMocks,
}) => {
  const page = new ClassifyWorkflowPage(authedPage);

  await apiMocks.datasets.mockGetDataset(datasetId, {
    ls_project_id: "100",
    ls_project_url: "http://localhost:8080/projects/100",
  });
  await apiMocks.datasets.mockListSamples(datasetId, [
    makeSample(datasetId, 0, { id: "sample-review-1" }),
    makeSample(datasetId, 1, { id: "sample-review-2" }),
  ]);
  await apiMocks.datasets.mockAnnotationStats(datasetId, {
    total_samples: 2,
    annotated_samples: 0,
    unlabeled_samples: 2,
  });
  await apiMocks.datasets.mockDatasetQuery(datasetId);

  await apiMocks.prediction.mockListModels([
    makeModel({
      id: modelId,
      uri: "memory://models/model-review-1",
      job_id: "job-review-1",
      dataset_id: datasetId,
      dataset_name: "flowers-dataset",
    }),
  ]);
  await apiMocks.prediction.mockListPredictionJobs([]);
  await apiMocks.prediction.mockRunPrediction(datasetId, modelId, predictionJobId);
  await apiMocks.prediction.mockGetPredictionJob(predictionJobId, {
    status: "completed",
    created_by: "user-e2e-1",
    summary: {
      processed: 2,
      total_samples: 2,
      predictions: reviewPredictions,
    },
  });
  await apiMocks.prediction.mockTaskTracker(predictionJobId);

  await apiMocks.training.mockListTrainingJobs([]);
  await apiMocks.training.mockListTrainers();

  await page.goto(`/datasets/${datasetId}/classify`);
  await page.waitForLoaded();

  await expect(page.getRunPredictionsButton()).toBeVisible();
  await expect(page.getGridRadio()).toBeVisible();
  await expect(page.getListRadio()).toBeVisible();
  await expect(page.getSidebarToggle()).toBeVisible();

  await authedPage.waitForSelector("[data-sb-item]");
  const itemCount = await page.getSampleBrowserItems().count();
  expect(itemCount).toBeGreaterThan(0);

  await expect(page.getWaferMapPanel()).toBeVisible();
  await expect(page.getWaferMapCanvas()).toBeVisible();
  await expect(page.getWaferMapPanel()).not.toContainText("No wafer points");

  await page.selectModel("flower-classifier");
  await page.clickRunPredictions();

  await expect(page.getPredictionSubmittedMessage()).toBeVisible();
  await expect(page.getReviewReadyMessage()).toBeVisible();
  await expect(page.getPredictionReviewMode()).toBeVisible();

  const agGrid = page.getAgGrid().first();
  await expect(agGrid).toContainText("rose");
  await expect(agGrid).toContainText("tulip");
  await expect(page.getSubmitButton()).toBeVisible();
});
