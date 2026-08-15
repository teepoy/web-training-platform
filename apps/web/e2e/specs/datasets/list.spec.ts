import { test, expect } from "../../fixtures";
import { DatasetListPage } from "../../pages/datasets/DatasetListPage";
import { DatasetDetailPage } from "../../pages/datasets/DatasetDetailPage";
import { makeFlowerDataset } from "../../mocks/factories";
import { createDataset, cleanupTestArtifacts } from "../../seed";

// ═══════════════════════════════════════════════════════════════════
// @mock tests — dataset list interactions with mocked backend
// ═══════════════════════════════════════════════════════════════════

test("dataset list renders current table surface @mock", async ({ authedPage }) => {
  const listPage = new DatasetListPage(authedPage);
  await listPage.goto("/datasets");
  await listPage.waitForLoaded();

  await expect(authedPage.getByRole("heading", { name: "Datasets" })).toBeVisible();
  await expect(authedPage.getByText("flowers-dataset")).toBeVisible();
  await expect(authedPage.getByRole("button", { name: "View", exact: true })).toBeVisible();
  await expect(authedPage.getByRole("button", { name: "Import Dataset" })).toHaveCount(0);
  await expect(authedPage.getByRole("button", { name: "Preview Dataset" })).toHaveCount(0);
  await expect(authedPage.getByRole("button", { name: "Delete" })).toBeVisible();
  await expect(authedPage.getByRole("button", { name: "Rename" })).toBeVisible();
});

test("dataset search and creator filters apply before pagination @mock", async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.datasets.mockListDatasets([
    makeFlowerDataset({
      id: "dataset-alpha",
      name: "Alpha Flowers",
      created_by: "user-e2e-1",
      creator_name: "E2E User",
    }),
    makeFlowerDataset({
      id: "dataset-beta",
      name: "Beta Flowers",
      created_by: "user-bob",
      creator_name: "Bob",
    }),
  ]);
  const listPage = new DatasetListPage(authedPage);
  await listPage.goto("/datasets");
  await listPage.waitForLoaded();

  await authedPage.getByPlaceholder("Search datasets").fill("alpha");
  await expect(authedPage.getByText("Alpha Flowers")).toBeVisible();
  await expect(authedPage.getByText("Beta Flowers")).toHaveCount(0);

  await authedPage.getByPlaceholder("Search datasets").clear();
  await authedPage.locator(".dataset-list-creator").click();
  await authedPage.getByText("Bob", { exact: true }).last().click();
  await expect(authedPage.getByText("Beta Flowers")).toBeVisible();
  await expect(authedPage.getByText("Alpha Flowers")).toHaveCount(0);
});

test("row view button navigates to dataset detail @mock", async ({ authedPage, apiMocks }) => {
  const dataset = makeFlowerDataset();
  const datasetId = dataset.id!;
  await apiMocks.datasets.mockGetDataset(datasetId);

  const listPage = new DatasetListPage(authedPage);
  await listPage.goto("/datasets");
  await listPage.waitForLoaded();
  await listPage.expectDatasetVisible(dataset.name!);

  await listPage.clickView();

  await expect(authedPage).toHaveURL(new RegExp(`/datasets/${datasetId}`));
});

test("non-creator hides owner-only row actions @mock", async ({ authedPage, apiMocks }) => {
  await apiMocks.auth.mockAuthMe({
    id: "user-admin-other",
    name: "Other Admin",
    email: "other-admin@example.com",
    is_superadmin: true,
  });

  const listPage = new DatasetListPage(authedPage);
  await listPage.goto("/datasets");
  await listPage.waitForLoaded();
  await authedPage.locator(".dataset-list-creator .n-base-clear").click();
  await listPage.expectDatasetVisible("flowers-dataset");

  await listPage.expectPublicControlsHidden();
  await expect(authedPage.getByRole("button", { name: "Delete" })).toHaveCount(0);
  await expect(authedPage.getByRole("button", { name: "Rename" })).toHaveCount(0);
});

test("selects and deletes multiple owned datasets without opening a row @mock", async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.datasets.mockListDatasets([
    makeFlowerDataset({ id: "dataset-bulk-1", name: "Bulk Flowers One" }),
    makeFlowerDataset({ id: "dataset-bulk-2", name: "Bulk Flowers Two" }),
  ]);
  const listPage = new DatasetListPage(authedPage);
  await listPage.goto("/datasets");
  await listPage.waitForLoaded();

  const rowCheckboxes = authedPage.getByRole("checkbox");
  await rowCheckboxes.nth(1).check();
  await rowCheckboxes.nth(2).check();
  await expect(authedPage).toHaveURL(/\/datasets$/);
  await expect(authedPage.getByText("2 datasets selected")).toBeVisible();

  authedPage.once("dialog", (dialog) => dialog.accept());
  await authedPage.getByRole("button", { name: "Delete selected" }).click();

  await expect(authedPage.getByText("Bulk Flowers One")).toHaveCount(0);
  await expect(authedPage.getByText("Bulk Flowers Two")).toHaveCount(0);
  await expect(authedPage.getByTestId("bulk-selection-toolbar")).toHaveCount(0);
});

// ═══════════════════════════════════════════════════════════════════
// @live tests — dataset interactions against real backend
// ═══════════════════════════════════════════════════════════════════

test("API-created dataset appears in live list @live", async ({
  page,
  seedClient: _sc,
  testPrefix,
}) => {
  const name = `${testPrefix}-list`;
  await createDataset({
    name,
    dataset_type: "image_classification",
    task_spec: { task_type: "classification", label_space: ["cat", "dog"] },
  });

  try {
    const listPage = new DatasetListPage(page);
    await listPage.goto("/datasets");
    await listPage.waitForLoaded();
    await listPage.expectDatasetVisible(name);
  } finally {
    await cleanupTestArtifacts(testPrefix);
  }
});

test("view dataset detail @live", async ({ page, seedClient: _sc, testPrefix }) => {
  const name = `${testPrefix}-detail`;

  // Create dataset via API so we only test the detail view, not the import flow.
  // _sc (seedClient) configures orval fetcher with auth token.
  const dataset = await createDataset({
    name,
    dataset_type: "image_classification",
    task_spec: { task_type: "classification", label_space: ["cat", "dog"] },
  });

  // Cleanup after the test.
  try {
    const detailPage = new DatasetDetailPage(page);
    await detailPage.gotoDetail(dataset.id!);
    await detailPage.waitForLoaded();

    const tabs = page.locator(".n-tabs-tab");
    await expect(tabs.filter({ hasText: "Samples" })).toBeVisible();
    await expect(tabs.filter({ hasText: "Train" })).toBeVisible();
    await expect(tabs.filter({ hasText: "Predict" })).toBeVisible();
    await expect(tabs.filter({ hasText: "Annotate" })).toBeVisible();
  } finally {
    await cleanupTestArtifacts(testPrefix);
  }
});
