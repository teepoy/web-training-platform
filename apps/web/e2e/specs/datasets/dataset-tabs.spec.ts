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
    creator_name: "E2E User",
  });

  await page.gotoDetail(datasetId);
  await page.waitForLoaded();

  await expect(
    authedPage.locator(".n-tabs .n-tabs-tab").filter({ hasText: "Overview" }),
  ).toBeVisible();
  await expect(authedPage.getByText("About this dataset", { exact: true }).first()).toBeVisible();
  await expect(authedPage.getByText("E2E User", { exact: true })).toBeVisible();
  await expect(authedPage.getByText("rose", { exact: true })).toBeVisible();
  await expect(authedPage.getByText("Storage mode", { exact: true })).toHaveCount(0);
  await expect(authedPage.getByText("Available views", { exact: true })).toHaveCount(0);
  await expect(authedPage.getByText("Change record", { exact: true })).toHaveCount(0);
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
  await expect(authedPage).toHaveURL(new RegExp(`/datasets/${datasetId}#predict$`));

  await expect(authedPage.getByText("Prediction runs", { exact: true })).toBeVisible();
  await expect(authedPage.getByText("Prediction Jobs", { exact: true })).not.toBeVisible();

  const startButton = page.getStartPredictionButton();
  await expect(startButton).toBeVisible();

  await startButton.click();

  await expect(authedPage.getByRole("dialog")).toBeVisible();

  const dialog = authedPage.getByRole("dialog");
  const dialogBox = await dialog.boundingBox();
  expect(dialogBox).not.toBeNull();
  expect((dialogBox?.y ?? 0) + (dialogBox?.height ?? 0)).toBeLessThanOrEqual(
    authedPage.viewportSize()?.height ?? 720,
  );
  await expect(dialog.getByRole("button", { name: "Cancel" })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Start with selected model" })).toBeVisible();
  await expect(dialog.getByRole("columnheader", { name: "Model" })).toBeVisible();
  await expect(dialog.getByPlaceholder(/Search model name/)).toBeVisible();
  await expect(dialog.getByText("Demo Model", { exact: true })).toBeVisible();
  await dialog.getByText("Demo Model", { exact: true }).click();
  await expect(dialog.getByRole("button", { name: "Start with selected model" })).toBeEnabled();
});

test("SC Export tab offers Parquet, KLARF, and ZIP result exports @mock", async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.datasets.mockGetDataset(datasetId, {
    dataset_type: "image_sc",
    storage_mode: "file_shard_sparse",
    task_spec: { task_type: "sc", label_space: ["0", "60"] },
  });
  await apiMocks.datasets.mockDatasetStatus(datasetId);
  await apiMocks.prediction.mockListPredictionJobs([]);
  await apiMocks.prediction.mockListModels([]);

  await authedPage.goto(`/datasets/${datasetId}#export`);
  await expect(authedPage.getByTestId("dataset-prediction-export-tab")).toBeVisible();
  await expect(authedPage).toHaveURL(new RegExp(`/datasets/${datasetId}#export$`));
  await expect(authedPage.getByText("Prediction runs", { exact: true })).not.toBeVisible();
  await expect(authedPage.getByRole("dialog")).not.toBeVisible();

  const exportTab = authedPage.getByTestId("dataset-prediction-export-tab");

  await expect(exportTab.getByText("Export current results", { exact: true })).toBeVisible();
  await expect(
    exportTab.getByText("Choose the class result, optional Review Sampling, and file format."),
  ).toBeVisible();
  await expect(exportTab.getByRole("radio", { name: /^Parquet\b/ })).toBeVisible();
  const klarfOption = exportTab.getByRole("radio", { name: /^KLARF\b/ });
  await expect(klarfOption).toBeVisible();
  await expect(exportTab.getByRole("radio", { name: /^ZIP package\b/ })).toBeVisible();
  await klarfOption.click();
  await expect(exportTab.getByText("KLARF version", { exact: true })).toBeVisible();
  await expect(exportTab.getByLabel("KLARF version 1.2")).toBeVisible();
  await expect(exportTab.getByLabel("KLARF version 1.8")).toBeVisible();
  await expect(exportTab.getByLabel("Include defect images")).toBeVisible();
  await expect(exportTab.getByText("Review Sampling", { exact: true })).toBeVisible();
  await expect(exportTab.getByText(/One defective patch per retained row/)).toBeVisible();
  await expect(exportTab.getByText(/Large exports can exceed 100 MB/)).toBeVisible();
});

test("SC-only export stays hidden for a generic sparse Dataset @mock", async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.datasets.mockGetDataset(datasetId, {
    dataset_type: "image_classification",
    storage_mode: "file_shard_sparse",
    task_spec: { task_type: "sc", label_space: ["0", "60"] },
    view_types: ["image_input_v1"],
  });

  await authedPage.goto(`/datasets/${datasetId}#export`);

  await expect(authedPage.locator(".n-tabs-tab").filter({ hasText: /^Export$/ })).toHaveCount(0);
  await expect(authedPage.getByTestId("dataset-prediction-export-tab")).toHaveCount(0);
  await expect(authedPage).toHaveURL(new RegExp(`/datasets/${datasetId}#overview$`));
});

test("SC Classify tab opens the workspace directly @mock", async ({ authedPage, apiMocks }) => {
  await apiMocks.datasets.mockGetDataset(datasetId, {
    name: "Inspection samples",
    dataset_type: "image_sc",
    storage_mode: "file_shard_sparse",
    task_spec: { task_type: "sc", label_space: ["0", "60"] },
    view_types: ["image_input_v1", "patch_image_v1", "review_image_v1"],
  });

  await authedPage.goto(`/datasets/${datasetId}#overview`);

  await authedPage
    .locator(".n-tabs-tab")
    .filter({ hasText: /^Classify/ })
    .click();
  await expect(authedPage).toHaveURL(new RegExp(`/datasets/${datasetId}/sc/classify$`));
  await expect(authedPage.getByTestId("classify-workspace-launcher")).toHaveCount(0);
});

test("Dataset detail restores the selected tab from the URL hash @mock", async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.datasets.mockGetDataset(datasetId, {
    task_spec: { task_type: "classification", label_space: ["rose", "tulip"] },
  });
  await apiMocks.datasets.mockDatasetStatus(datasetId);
  await apiMocks.prediction.mockListPredictionJobs([]);
  await apiMocks.prediction.mockListModels([]);

  await authedPage.goto(`/datasets/${datasetId}#predict`);

  await expect(authedPage.getByText("Prediction runs", { exact: true })).toBeVisible();
  await expect(authedPage).toHaveURL(new RegExp(`/datasets/${datasetId}#predict$`));
});

test("Prediction model picker can page to older models @mock", async ({ authedPage, apiMocks }) => {
  const page = new DatasetDetailPage(authedPage);
  await apiMocks.datasets.mockGetDataset(datasetId, {
    task_spec: { task_type: "classification", label_space: ["rose", "tulip"] },
  });
  await apiMocks.datasets.mockDatasetStatus(datasetId);
  await apiMocks.prediction.mockListPredictionJobs([]);
  await apiMocks.prediction.mockListModels([
    makeModel({ id: "old-model", name: "Historical baseline", created_at: "2020-01-01T00:00:00Z" }),
    ...Array.from({ length: 20 }, (_, index) =>
      makeModel({
        id: `new-model-${index}`,
        name: `Recent model ${index}`,
        created_at: `2026-01-${String(index + 1).padStart(2, "0")}T00:00:00Z`,
      }),
    ),
  ]);

  await page.gotoDetail(datasetId);
  await page.gotoPredictTab();
  await page.getStartPredictionButton().click();
  const dialog = authedPage.getByRole("dialog");
  await dialog.locator(".n-pagination-item").filter({ hasText: "2" }).click();

  await expect(dialog.getByText("Historical baseline", { exact: true })).toBeVisible();
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
