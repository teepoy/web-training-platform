import type { Locator, Page } from "@playwright/test";
import { expect, test } from "../../fixtures";
import { ReclassifyPagePom } from "../../pages/sc/ReclassifyPagePom";
import {
  mockListTrainers,
  mockScDataset,
  mockScDefectIds,
  mockScPlotPoints,
  mockScSamplesWithLabels,
  mockScViewSamplesPaged,
} from "../../mocks/handlers";

const DATASET_ID = "export-global-filter";

test.beforeEach(async ({ authedPage }) => {
  await mockListTrainers(authedPage);
  await mockScDataset(authedPage, DATASET_ID);
  await mockScPlotPoints(authedPage, DATASET_ID, 20);
  await mockScDefectIds(authedPage, DATASET_ID, 20);
  await mockScViewSamplesPaged(authedPage, DATASET_ID, "patch_image_v1", 20, 20);
  await mockScSamplesWithLabels(authedPage, DATASET_ID, 20, 20);
});

async function addRoughBinFilter(root: Locator): Promise<void> {
  await root.getByTestId("query-add-condition").click();
  await root.getByTestId("query-rule-property").click();
  await root.getByTestId("query-rule-property").locator("input").fill("Rough Bin");
  await root.page().getByText("Rough Bin", { exact: true }).last().click();
  await root.getByRole("checkbox", { name: "2" }).check();
  await root.getByRole("button", { name: "Apply", exact: true }).click();
}

async function openExport(page: Page): Promise<Locator> {
  await page.getByTestId("sc-classify-export").click();
  const modal = page.getByTestId("flow-modal");
  await modal.getByRole("button", { name: "Export current results" }).click();
  await expect(page.getByTestId("sc-prediction-export")).toBeVisible();
  return modal;
}

async function mockExport(page: Page, requests: Array<Record<string, unknown>>): Promise<void> {
  await page.route(
    `**/api/v1/sc/datasets/${DATASET_ID}/prediction-exports/stream`,
    async (route) => {
      requests.push(route.request().postDataJSON() as Record<string, unknown>);
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: 'event: done\ndata: {"event_type":"done","payload":{"uri":"memory://export.parquet","rows":4,"format":"parquet","filename":"export.parquet","sampled":true,"klarf_version":null}}\n\n',
      });
    },
  );
}

test("top-bar Global Filter reaches export independently of Review Sampling @mock", async ({
  authedPage,
}) => {
  const requests: Array<Record<string, unknown>> = [];
  await mockExport(authedPage, requests);
  const page = new ReclassifyPagePom(authedPage);
  await page.gotoReclassify(DATASET_ID);

  await authedPage.getByTestId("sc-global-filter-trigger").click();
  const filterModal = authedPage.getByTestId("sc-global-filter-modal");
  await addRoughBinFilter(filterModal);
  await filterModal.getByTestId("sc-global-filter-apply").click();
  const exportModal = await openExport(authedPage);
  await exportModal.getByRole("button", { name: "Create export" }).click();

  await expect.poll(() => requests.length).toBe(1);
  expect(requests[0]).toMatchObject({
    sample_filter: {
      combinator: "and",
      items: [expect.objectContaining({ field: "rough_bin" })],
    },
    sampling: null,
  });
});

test("Review Sampling Extra Filter offers columns and reaches export @mock", async ({
  authedPage,
}) => {
  const requests: Array<Record<string, unknown>> = [];
  await mockExport(authedPage, requests);
  const page = new ReclassifyPagePom(authedPage);
  await page.gotoReclassify(DATASET_ID);

  const exportModal = await openExport(authedPage);
  await exportModal.getByRole("button", { name: "Configure" }).click();
  const samplingModal = authedPage.getByTestId("review-sampling-modal");
  await samplingModal.getByText("Extra filter", { exact: true }).first().click();
  await addRoughBinFilter(samplingModal);
  await samplingModal.getByRole("button", { name: "Apply sampling" }).click();
  await exportModal.getByRole("button", { name: "Create export" }).click();

  await expect.poll(() => requests.length).toBe(1);
  expect(requests[0]).toMatchObject({
    sampling: {
      extra_filter: {
        combinator: "and",
        items: [
          {
            kind: "condition",
            field: "rough_bin",
            condition: { filterType: "set", values: [2] },
          },
        ],
      },
    },
  });
});
