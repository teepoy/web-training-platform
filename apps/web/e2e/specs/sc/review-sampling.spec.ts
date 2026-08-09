import { test, expect } from "../../fixtures";
import { tableFromArrays, tableToIPC } from "apache-arrow";
import { ReclassifyPagePom } from "../../pages/sc/ReclassifyPagePom";
import {
  mockScDataset,
  mockScDefectIds,
  mockScPlotPoints,
  mockScSamplesWithLabels,
  mockScViewSamplesPaged,
} from "../../mocks/handlers";

const DATASET_ID = "sampling-rules-sc";

test("Global Filter waits for explicit confirmation before refreshing consumers @mock", async ({
  authedPage,
}) => {
  await mockScDataset(authedPage, DATASET_ID);
  await mockScPlotPoints(authedPage, DATASET_ID, 20);
  await mockScDefectIds(authedPage, DATASET_ID, 20);
  await mockScViewSamplesPaged(authedPage, DATASET_ID, "patch_image_v1", 20, 20);
  await mockScSamplesWithLabels(authedPage, DATASET_ID, 20, 20);

  const filteredRequests: Array<{ description?: string; sql: string }> = [];
  authedPage.on("request", (request) => {
    if (!request.url().includes(`/api/v1/sc/data/datasets/${DATASET_ID}/query`)) return;
    const body = request.postDataJSON() as { description?: string; sql: string } | null;
    if (body?.sql.includes('"rough_bin" = ANY(?)')) filteredRequests.push(body);
  });

  const page = new ReclassifyPagePom(authedPage);
  await page.gotoReclassify(DATASET_ID);
  await expect(authedPage.getByTestId("sc-global-filter-trigger")).toHaveText("Global Filter");
  await authedPage.getByTestId("sc-global-filter-trigger").click();
  const modal = authedPage.getByTestId("sc-global-filter-modal");
  const addRoughBinDraft = async () => {
    await modal.getByTestId("query-add-condition").click();
    await modal.getByTestId("query-rule-property").click();
    await modal.getByTestId("query-rule-property").locator("input").fill("Rough Bin");
    await authedPage.getByText("Rough Bin", { exact: true }).click();
    await modal.getByRole("checkbox", { name: "2" }).check();
    await modal.getByRole("button", { name: "Apply", exact: true }).click();
  };

  await expect(modal.getByRole("button", { name: "close", exact: true })).toBeVisible();
  await addRoughBinDraft();
  expect(filteredRequests).toHaveLength(0);
  await modal.getByRole("button", { name: "close", exact: true }).click();
  await expect(modal).toBeHidden();
  await expect(authedPage.getByTestId("sc-global-filter-trigger")).toHaveText("Global Filter");

  await authedPage.getByTestId("sc-global-filter-trigger").click();
  await expect(modal.getByText("No conditions", { exact: true })).toBeVisible();
  await addRoughBinDraft();

  await expect(modal.getByText("Rough Bin", { exact: true })).toBeVisible();
  expect(filteredRequests).toHaveLength(0);
  await expect(authedPage.getByTestId("sc-global-filter-trigger")).toHaveText("Global Filter");

  await modal.getByTestId("sc-global-filter-apply").click();

  await expect
    .poll(
      () => filteredRequests.filter((request) => request.description === "sc-workbench.map").length,
    )
    .toBeGreaterThan(0);
  await expect(authedPage.getByTestId("sc-global-filter-trigger")).toHaveText("Global Filter (1)");
});

test("Train & Predict submits the page-owned Global Filter @mock", async ({
  authedPage,
  apiMocks,
}) => {
  await mockScDataset(authedPage, DATASET_ID);
  await mockScPlotPoints(authedPage, DATASET_ID, 20);
  await mockScDefectIds(authedPage, DATASET_ID, 20);
  await mockScViewSamplesPaged(authedPage, DATASET_ID, "patch_image_v1", 20, 20);
  await mockScSamplesWithLabels(authedPage, DATASET_ID, 20, 20);
  await apiMocks.datasets.mockAnnotationStats(DATASET_ID, {
    total_samples: 20,
    annotated_samples: 10,
    unlabeled_samples: 10,
    label_counts: { Scratch: 5, Particle: 5 },
  });
  await apiMocks.training.mockListTrainers([
    {
      id: "resnet50-sc-e2e",
      name: "ResNet-50 SC",
      trainable: true,
      view_type: "patch_image_v1",
    },
  ]);

  const workflowRequests: Array<Record<string, unknown>> = [];
  await authedPage.route("**/api/v1/training-jobs/train-and-predict", async (route) => {
    workflowRequests.push(route.request().postDataJSON() as Record<string, unknown>);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        train_job: { id: "train-filter-e2e", status: "queued" },
        workflow_run_id: "workflow-filter-e2e",
      }),
    });
  });

  const page = new ReclassifyPagePom(authedPage);
  await page.gotoReclassify(DATASET_ID);
  await expect(authedPage.getByTestId("sc-train-predict")).toBeEnabled();

  await authedPage.getByTestId("sc-global-filter-trigger").click();
  const filterModal = authedPage.getByTestId("sc-global-filter-modal");
  await filterModal.getByTestId("query-add-condition").click();
  await filterModal.getByTestId("query-rule-property").click();
  await filterModal.getByTestId("query-rule-property").locator("input").fill("Rough Bin");
  await authedPage.getByText("Rough Bin", { exact: true }).click();
  await filterModal.getByRole("checkbox", { name: "2" }).check();
  await filterModal.getByRole("button", { name: "Apply", exact: true }).click();
  await filterModal.getByTestId("sc-global-filter-apply").click();
  await expect(authedPage.getByTestId("sc-global-filter-trigger")).toHaveText("Global Filter (1)");

  await authedPage.getByTestId("sc-train-predict").click();
  const confirmation = authedPage.getByText("Filtered Train & Predict", { exact: true });
  await expect(confirmation).toBeVisible();
  await authedPage.getByRole("button", { name: /Continue with \d+ defects/ }).click();

  await expect.poll(() => workflowRequests.length).toBe(1);
  expect(workflowRequests[0]).toMatchObject({
    dataset_id: DATASET_ID,
    trainer_id: "resnet50-sc-e2e",
    sample_filter: {
      combinator: "and",
      items: [
        {
          kind: "condition",
          field: "rough_bin",
          condition: { filterType: "set", values: [2] },
        },
      ],
    },
  });
});

test("map selection filters the table and continuously accumulates exclusions @mock", async ({
  authedPage,
}) => {
  await mockScDataset(authedPage, DATASET_ID);
  await mockScPlotPoints(authedPage, DATASET_ID, 20);
  await mockScDefectIds(authedPage, DATASET_ID, 20);
  await mockScViewSamplesPaged(authedPage, DATASET_ID, "patch_image_v1", 20, 20);
  await mockScSamplesWithLabels(authedPage, DATASET_ID, 20, 20);

  let areaSelectionCount = 0;
  await authedPage.route(`**/api/v1/sc/data/datasets/${DATASET_ID}/query`, async (route) => {
    const body = route.request().postDataJSON() as { description?: string } | null;
    if (body?.description !== "sc-workbench.selection.rectangle") {
      await route.fallback();
      return;
    }
    areaSelectionCount += 1;
    const defectIds = areaSelectionCount === 1 ? [1, 2] : [3, 4];
    await route.fulfill({
      status: 200,
      contentType: "application/vnd.apache.arrow.stream",
      headers: { "X-SC-Data-Revision": "0" },
      body: Buffer.from(tableToIPC(tableFromArrays({ defect_id: defectIds }))),
    });
  });

  const tableRequests: Array<{ sql: string; parameters: unknown[] }> = [];
  const mapRequests: Array<{ sql: string; parameters: unknown[] }> = [];
  authedPage.on("request", (request) => {
    if (!request.url().includes(`/api/v1/sc/data/datasets/${DATASET_ID}/query`)) return;
    const body = request.postDataJSON() as {
      description?: string;
      sql: string;
      parameters: unknown[];
    } | null;
    if (body?.description === "sc-workbench.table.rows") tableRequests.push(body);
    if (body?.description === "sc-workbench.map") mapRequests.push(body);
  });

  const page = new ReclassifyPagePom(authedPage);
  await page.gotoReclassify(DATASET_ID);
  const map = authedPage.getByTestId("sc-unified-map");
  const emitBoxSelection = async () => {
    await map.evaluate((element) => {
      element.dispatchEvent(
        new CustomEvent("box-select", {
          detail: { x: 0, y: 0, w: 10, h: 10 },
          bubbles: true,
        }),
      );
    });
  };

  await emitBoxSelection();
  await expect
    .poll(() =>
      tableRequests.some(
        (body) =>
          body.sql.includes('"map_id" = ANY(?)') &&
          body.parameters.some((value) => JSON.stringify(value) === "[1,2]"),
      ),
    )
    .toBe(true);

  const excludeSelected = async () => {
    await map.evaluate((element) => {
      element.dispatchEvent(
        new CustomEvent("map-context-menu", {
          detail: { x: 120, y: 240 },
          bubbles: true,
        }),
      );
    });
    await authedPage.getByText("Exclude selected", { exact: true }).click();
  };
  await excludeSelected();
  await expect
    .poll(() => tableRequests.some((body) => body.sql.includes('NOT ("map_id" = ANY(?))')))
    .toBe(true);
  await expect
    .poll(() =>
      mapRequests.some(
        (body) =>
          body.sql.includes('NOT ("map_id" = ANY(?))') &&
          body.parameters.some((value) => JSON.stringify(value) === "[1,2]"),
      ),
    )
    .toBe(true);

  await emitBoxSelection();
  await expect
    .poll(() =>
      tableRequests.some(
        (body) =>
          body.sql.includes('NOT ("map_id" = ANY(?))') &&
          body.parameters.some((value) => JSON.stringify(value) === "[1,2]") &&
          body.parameters.some((value) => JSON.stringify(value) === "[3,4]"),
      ),
    )
    .toBe(true);
  await excludeSelected();
  await expect
    .poll(() =>
      mapRequests.some(
        (body) =>
          body.sql.includes('NOT ("map_id" = ANY(?))') &&
          body.parameters.some((value) => JSON.stringify(value) === "[1,2]") &&
          body.parameters.some((value) => JSON.stringify(value) === "[3,4]"),
      ),
    )
    .toBe(true);
  await expect(authedPage.getByTestId("sc-global-filter-trigger")).toHaveText("Global Filter (2)");
});

test("Review Sampling manages rules and applies the SQL pipeline from Reclassify @mock", async ({
  authedPage,
}) => {
  await mockScDataset(authedPage, DATASET_ID, {
    name: "Sampling Rules Dataset",
    label_space: ["Scratch", "Clean"],
  });
  await mockScPlotPoints(authedPage, DATASET_ID, 1000);
  await mockScDefectIds(authedPage, DATASET_ID, 1000);
  await mockScViewSamplesPaged(authedPage, DATASET_ID, "patch_image_v1", 1000, 200);
  await mockScSamplesWithLabels(authedPage, DATASET_ID, 1000, 200);

  const dataRequests: Array<{
    description?: string;
    sql: string;
    parameters?: unknown[];
  }> = [];
  authedPage.on("request", (request) => {
    if (!request.url().includes(`/api/v1/sc/data/datasets/${DATASET_ID}/query`)) return;
    const body = request.postDataJSON() as (typeof dataRequests)[number] | null;
    if (body) dataRequests.push(body);
  });

  const page = new ReclassifyPagePom(authedPage);
  await page.gotoReclassify(DATASET_ID);
  const filterActions = authedPage.getByTestId("sc-filter-actions");
  await expect(filterActions.getByTestId("sc-global-filter-trigger")).toBeVisible();
  await expect(filterActions).toBeVisible();
  await expect(page.randomFilterButton).toHaveText("Random Filter");
  await expect(page.clearRandomFilterButton).toHaveCount(0);
  await expect
    .poll(() => dataRequests.filter((body) => body.description === "sc-workbench.map").length)
    .toBe(1);

  await authedPage.getByText("Review", { exact: true }).click();
  await expect
    .poll(
      () =>
        dataRequests.filter(
          (body) =>
            body.description === "sc-workbench.table.rows" && body.sql.includes('"images" > ?'),
        ).length,
    )
    .toBeGreaterThan(0);
  expect(dataRequests.filter((body) => body.description === "sc-workbench.map")).toHaveLength(1);

  await page.openReviewSampling();

  await expect(page.reviewSamplingDialog.getByText("BASE ELIGIBLE")).toHaveCount(0);
  await expect(page.reviewSamplingDialog.getByText("Random seed")).toHaveCount(0);
  await page.reviewSamplingDialog.getByText("After sampling", { exact: true }).click();
  await expect(page.reviewSamplingDialog.getByTestId("sampling-assign-draft-label")).toBeChecked();
  await expect(page.reviewSamplingDialog.getByTestId("sampling-draft-label")).toContainText(
    "0 · Unclassified",
  );
  await page.reviewSamplingDialog.getByText("Enabled rules", { exact: true }).click();
  await expect(page.reviewSamplingDialog.getByRole("radio", { name: "All" })).toBeChecked();
  await expect(
    page.reviewSamplingDialog.getByTestId("sampling-total-limit").locator("input"),
  ).toHaveValue("200");
  await page.reviewSamplingDialog.getByRole("button", { name: "Manage sampling rules" }).click();
  await expect(authedPage.getByRole("listbox", { name: "Disabled sampling rules" })).toBeVisible();
  await expect(authedPage.getByRole("listbox", { name: "Enabled sampling rules" })).toBeVisible();

  await authedPage
    .getByTestId("manage-sampling-rules-modal")
    .getByRole("button", { name: "Done" })
    .click();
  await page.reviewSamplingDialog.getByText("Extra filter", { exact: true }).click();
  await expect(page.reviewSamplingDialog.getByText("Extra filter", { exact: true })).toHaveCount(2);
  await expect(page.reviewSamplingDialog.getByTestId("query-add-condition")).toBeVisible();
  await expect(page.reviewSamplingDialog.getByTestId("query-add-group")).toBeVisible();
  await page.reviewSamplingDialog.getByText("Enabled rules", { exact: true }).click();
  const mapRequestsBeforeSampling = dataRequests.filter(
    (body) => body.description === "sc-workbench.map",
  ).length;
  await page.reviewSamplingDialog.getByRole("button", { name: "Apply sampling" }).click();

  await expect(page.randomFilterButton).toHaveText("Random Filter (200)");
  await expect(page.clearRandomFilterButton).toHaveText("Clear");
  await expect
    .poll(
      () =>
        dataRequests.filter(
          (body) =>
            body.description === "sc-workbench.table.rows" &&
            body.sql.includes('"map_id" = ANY(?)'),
        ).length,
    )
    .toBeGreaterThan(0);
  expect(dataRequests.filter((body) => body.description === "sc-workbench.map")).toHaveLength(
    mapRequestsBeforeSampling,
  );
  const samplingRequests = dataRequests.filter(
    (body) => body.description === "sc-workbench.selection.sampling-program",
  );
  expect(samplingRequests).toHaveLength(1);
  expect(samplingRequests[0]?.sql).toContain('WITH "__sc_sampling_base" AS');
  expect(samplingRequests[0]?.sql).toContain('ORDER BY HASH("map_id", ?)');
  expect(samplingRequests[0]?.parameters).toContain(42);

  await page.clearRandomFilterButton.click();
  await expect(page.randomFilterButton).toHaveText("Random Filter");
  await expect(page.clearRandomFilterButton).toHaveCount(0);
});
