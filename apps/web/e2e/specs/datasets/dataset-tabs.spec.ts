import { test, expect } from "../../fixtures";
import { DatasetDetailPage } from "../../pages/datasets/DatasetDetailPage";
import { makeModel, makePredictionJob } from "../../mocks/factories";

const datasetId = "dataset-tabs-1";

test("Dataset detail opens on an overview of its persisted contract @mock", async ({
  authedPage,
  apiMocks,
}) => {
  const page = new DatasetDetailPage(authedPage);
  await apiMocks.datasets.mockGetDataset(datasetId, {
    task_spec: { task_type: "classification", label_space: ["rose", "tulip"] },
    view_types: ["image_input_v1"],
  });

  await page.gotoDetail(datasetId);
  await page.waitForLoaded();

  await expect(
    authedPage.locator(".n-tabs .n-tabs-tab").filter({ hasText: "Overview" }),
  ).toBeVisible();
  await expect(authedPage.getByText("Dataset type", { exact: true })).toBeVisible();
  await expect(authedPage.getByText("Storage mode", { exact: true })).toBeVisible();
  await expect(authedPage.getByText("rose", { exact: true })).toBeVisible();
});

test("Train tab does not block on sample-level readiness status @mock", async ({
  authedPage,
  apiMocks,
}) => {
  const page = new DatasetDetailPage(authedPage);

  await apiMocks.datasets.mockGetDataset(datasetId, {
    task_spec: { task_type: "classification", label_space: ["rose", "tulip"] },
  });
  await apiMocks.datasets.mockDatasetStatus(datasetId, {
    allow_train: false,
    train_disabled_reason: "insufficient_active_classes",
    minimum_active_class_count: 2,
    active_class_count: 0,
    annotated_samples: 0,
    total_samples: 10,
  });
  await apiMocks.training.mockListTrainingJobs([]);
  await apiMocks.training.mockListTrainers([]);

  await page.gotoDetail(datasetId);
  await page.waitForLoaded();

  await page.gotoTrainTab();
  await page.waitForTrainTabLoaded();

  await expect(authedPage.getByText("Training runs", { exact: true })).toBeVisible();
  await expect(authedPage.getByText("Training Jobs", { exact: true })).not.toBeVisible();

  const startButton = page.getStartJobButton();
  await expect(startButton).toBeVisible();
  await expect(startButton).toBeEnabled();
  await expect(
    authedPage.getByText("Training requires at least 2 active classes; currently 0."),
  ).not.toBeVisible();
});

test("Train tab enables Start New Job button when allowTrain=true @mock", async ({
  authedPage,
  apiMocks,
}) => {
  const page = new DatasetDetailPage(authedPage);

  await apiMocks.datasets.mockGetDataset(datasetId, {
    task_spec: { task_type: "classification", label_space: ["rose", "tulip"] },
  });
  await apiMocks.datasets.mockDatasetStatus(datasetId, {
    allow_train: true,
    train_disabled_reason: null,
    minimum_active_class_count: 2,
    active_class_count: 2,
    annotated_samples: 5,
    total_samples: 10,
  });
  await apiMocks.training.mockListTrainingJobs([]);
  await apiMocks.training.mockListTrainers([]);

  await page.gotoDetail(datasetId);
  await page.waitForLoaded();

  await page.gotoTrainTab();
  await page.waitForTrainTabLoaded();

  const startButton = page.getStartJobButton();
  await expect(startButton).toBeVisible();
  await expect(startButton).toBeEnabled();
});

test("Predict tab shows Start Prediction button and opens modal with model selector @mock", async ({
  authedPage,
  apiMocks,
}) => {
  const page = new DatasetDetailPage(authedPage);

  await apiMocks.datasets.mockGetDataset(datasetId, {
    task_spec: { task_type: "classification", label_space: ["rose", "tulip"] },
  });
  await apiMocks.datasets.mockDatasetStatus(datasetId);
  await apiMocks.prediction.mockListPredictionJobs([]);
  await apiMocks.training.mockListTrainingJobs([]);
  await apiMocks.prediction.mockListModels([
    makeModel({ id: "model-1", name: "Demo Model", dataset_id: datasetId }),
  ]);

  await page.gotoDetail(datasetId);
  await page.waitForLoaded();

  await page.gotoPredictTab();
  await page.waitForPredictTabLoaded();

  await expect(authedPage.getByText("Prediction runs", { exact: true })).toBeVisible();
  await expect(authedPage.getByText("Prediction Jobs", { exact: true })).not.toBeVisible();

  const startButton = page.getStartPredictionButton();
  await expect(startButton).toBeVisible();

  await startButton.click();

  await expect(authedPage.getByRole("dialog")).toBeVisible();

  const dialog = authedPage.getByRole("dialog");
  await expect(dialog.getByText("Model", { exact: true })).toBeVisible();
  await expect(dialog.getByText("Select a model")).toBeVisible();
  await dialog.locator(".n-select").click();
  await expect(authedPage.getByText("Demo Model", { exact: false }).last()).toBeVisible();
});

test("Predict tab only shows prediction jobs for the current dataset @mock", async ({
  authedPage,
  apiMocks,
}) => {
  const page = new DatasetDetailPage(authedPage);

  await apiMocks.datasets.mockGetDataset(datasetId, {
    task_spec: { task_type: "classification", label_space: ["rose", "tulip"] },
  });
  await apiMocks.datasets.mockDatasetStatus(datasetId);
  await apiMocks.prediction.mockListPredictionJobs([
    makePredictionJob({
      id: "current1-prediction-job",
      dataset_id: datasetId,
      status: "completed",
    }),
    makePredictionJob({
      id: "other999-prediction-job",
      dataset_id: "other-dataset",
      status: "completed",
    }),
  ]);
  await apiMocks.training.mockListTrainingJobs([]);

  await page.gotoDetail(datasetId);
  await page.waitForLoaded();

  await page.gotoPredictTab();
  await page.waitForPredictTabLoaded();

  await expect(authedPage.getByText("current1…")).toBeVisible();
  await expect(authedPage.getByText("other999…")).not.toBeVisible();
});

test("Task Explorer renders task table @mock", async ({ authedPage }) => {
  await authedPage.route("**/api/v1/task-tracker/tasks**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            id: "task-1",
            display_name: "Prediction task",
            dataset_id: datasetId,
            dataset_name: "flowers-dataset",
            display_status: "running",
            stage: "running",
            task_kind: "prediction",
            queue_priority_label: "none",
            updated_at: "2026-01-01T00:00:00Z",
          },
        ],
        total: 1,
      }),
    });
  });

  await authedPage.goto("/tasks?kind=prediction");

  await expect(authedPage.getByText("Task Explorer")).toBeVisible();
  await expect(authedPage.getByText("Prediction task")).toBeVisible();
  await expect(authedPage.getByRole("button", { name: "Insight" })).toBeVisible();
});

test("Train tab modal hides dataset selector when datasetId prop is set @mock", async ({
  authedPage,
  apiMocks,
}) => {
  const page = new DatasetDetailPage(authedPage);

  await apiMocks.datasets.mockGetDataset(datasetId, {
    task_spec: { task_type: "classification", label_space: ["rose", "tulip"] },
  });
  await apiMocks.datasets.mockDatasetStatus(datasetId, {
    allow_train: true,
    train_disabled_reason: null,
    minimum_active_class_count: 2,
    active_class_count: 2,
    annotated_samples: 5,
    total_samples: 10,
  });
  await apiMocks.training.mockListTrainingJobs([]);
  await apiMocks.training.mockListTrainers([]);

  await page.gotoDetail(datasetId);
  await page.waitForLoaded();

  await page.gotoTrainTab();
  await page.waitForTrainTabLoaded();

  const startButton = page.getStartJobButton();
  await startButton.click();

  await expect(authedPage.getByRole("dialog")).toBeVisible();

  // Dataset selector should NOT be visible — it's auto-set from props.datasetId
  const datasetFormLabel = authedPage.getByText("Dataset", { exact: true });
  await expect(datasetFormLabel).not.toBeVisible();
});
