import { test, expect } from "../../fixtures";
import { tableFromArrays, tableToIPC } from "apache-arrow";
import {
  mockListTrainers,
  mockScDataset,
  mockScDefectIds,
  mockScPlotPoints,
  mockScSamplesWithLabels,
  mockScViewSamplesPaged,
} from "../../mocks/handlers";

const datasetId = "sc-classify-1";

test.beforeEach(async ({ authedPage }) => {
  await mockListTrainers(authedPage);
});

test("SC classify page shows error state for missing dataset @mock", async ({ authedPage }) => {
  await authedPage.route(`**/api/v1/datasets/${datasetId}`, async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Not found" }),
    });
  });

  await authedPage.goto(`/datasets/${datasetId}/sc/classify`);
  await authedPage.waitForLoadState("domcontentloaded");

  await expect(authedPage.getByRole("button", { name: "Go Back" })).toBeVisible({
    timeout: 10_000,
  });
});

test("Global Filter persists with statistics from the dataset detail page @mock", async ({
  authedPage,
}) => {
  const cachedDatasetId = "sc-classify-cached-detail";
  await mockScDataset(authedPage, cachedDatasetId);
  await mockScPlotPoints(authedPage, cachedDatasetId, 20);
  await mockScDefectIds(authedPage, cachedDatasetId, 20);
  await mockScViewSamplesPaged(authedPage, cachedDatasetId, "patch_image_v1", 20, 20);
  await mockScSamplesWithLabels(authedPage, cachedDatasetId, 20, 20);
  await authedPage.route(`**/api/v1/sc/data/datasets/${cachedDatasetId}/query`, async (route) => {
    const request = route.request().postDataJSON() as { description?: string; sql?: string } | null;
    if (request?.description !== "sc-workbench.aggregate.class_number") {
      await route.fallback();
      return;
    }
    const filtered = request.sql?.includes('"rough_bin" = ANY(?)') ?? false;
    await route.fulfill({
      status: 200,
      contentType: "application/vnd.apache.arrow.stream",
      headers: { "X-SC-Data-Revision": "0" },
      body: Buffer.from(
        tableToIPC(
          tableFromArrays({
            group_key: [0],
            group_count: [filtered ? 8 : 20],
          }),
        ),
      ),
    });
  });

  const teleportWarnings: string[] = [];
  authedPage.on("console", (entry) => {
    if (entry.text().includes("Failed to locate Teleport target")) {
      teleportWarnings.push(entry.text());
    }
  });

  await authedPage.goto(`/datasets/${cachedDatasetId}`);
  await expect(authedPage.getByTestId("sc-dataset-global-filter-trigger")).toBeVisible();
  await expect(authedPage.getByTestId("sc-dataset-filter-stats")).toContainText("20 / 20 samples");

  await authedPage.getByTestId("sc-dataset-global-filter-trigger").click();
  const modal = authedPage.getByTestId("sc-global-filter-modal");
  await modal.getByTestId("query-add-condition").click();
  await modal.getByTestId("query-rule-property").click();
  await modal.getByTestId("query-rule-property").locator("input").fill("Rough Bin");
  await authedPage.getByText("Rough Bin", { exact: true }).click();
  await modal.getByRole("checkbox", { name: "2" }).check();
  await modal.getByRole("button", { name: "Apply", exact: true }).click();
  await modal.getByTestId("sc-global-filter-apply").click();

  const filterStats = authedPage.getByTestId("sc-dataset-filter-stats");
  await expect(filterStats).toContainText("8 / 20 samples");
  await expect(filterStats).toContainText("40%");
  await expect(filterStats).toContainText("12 excluded");

  await authedPage
    .locator(".n-tabs-tab")
    .filter({ hasText: /^Classify/ })
    .click();

  await expect(authedPage).toHaveURL(`/datasets/${cachedDatasetId}/sc/classify`);
  await expect(authedPage.getByTestId("sc-global-filter-trigger")).toHaveText("Global Filter (1)");
  expect(teleportWarnings).toEqual([]);
});

test("SC classify opens the current-results export flow from the header @mock", async ({
  authedPage,
}) => {
  const exportDatasetId = "sc-classify-export";
  await mockScDataset(authedPage, exportDatasetId);
  await mockScPlotPoints(authedPage, exportDatasetId, 20);
  await mockScDefectIds(authedPage, exportDatasetId, 20);
  await mockScViewSamplesPaged(authedPage, exportDatasetId, "patch_image_v1", 20, 20);
  await mockScSamplesWithLabels(authedPage, exportDatasetId, 20, 20);

  await authedPage.goto(`/datasets/${exportDatasetId}/sc/classify`);
  const selectAllGallery = authedPage.getByRole("button", { name: "Select all (1,000)" });
  await expect(selectAllGallery).toBeVisible();
  await selectAllGallery.click();
  await expect(authedPage.getByRole("button", { name: "Clear selection (1,000)" })).toBeVisible();

  const exportButton = authedPage.getByTestId("sc-classify-export");
  await expect(exportButton).toBeVisible();
  await exportButton.click();
  await expect(exportButton).toHaveAttribute("aria-expanded", "true");

  const exportDialog = authedPage.getByRole("dialog", { name: "Export current results" });
  await expect(exportDialog).toBeVisible();
  await exportDialog.getByRole("button", { name: "Export current results" }).click();
  await expect(exportDialog.getByText("Parquet", { exact: true })).toBeVisible();
  await expect(exportDialog.getByText("KLARF", { exact: true })).toBeVisible();
  await expect(exportDialog.getByText("ZIP package", { exact: true })).toBeVisible();
});
