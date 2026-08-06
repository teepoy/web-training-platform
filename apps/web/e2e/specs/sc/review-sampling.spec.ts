import { test, expect } from "../../fixtures";
import { ReclassifyPagePom } from "../../pages/sc/ReclassifyPagePom";
import {
  mockScDataset,
  mockScDefectIds,
  mockScPlotPoints,
  mockScSamplesWithLabels,
  mockScViewSamplesPaged,
} from "../../mocks/handlers";

const DATASET_ID = "sampling-rules-sc";

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

  const samplingRequests: Array<{ description?: string; sql: string }> = [];
  authedPage.on("request", (request) => {
    if (!request.url().includes(`/api/v1/sc/data/datasets/${DATASET_ID}/query`)) return;
    const body = request.postDataJSON() as { description?: string; sql: string } | null;
    if (body?.description === "sc-workbench.selection.sampling-program") {
      samplingRequests.push(body);
    }
  });

  const page = new ReclassifyPagePom(authedPage);
  await page.gotoReclassify(DATASET_ID);
  await page.openReviewSampling();

  await expect(page.reviewSamplingDialog.getByText("BASE ELIGIBLE")).toBeVisible();
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
  await page.reviewSamplingDialog.getByText("Global filter", { exact: true }).click();
  await expect(page.reviewSamplingDialog.getByText("Workbench Global Filter")).toBeVisible();
  await page.reviewSamplingDialog.getByText("Enabled rules", { exact: true }).click();
  await page.reviewSamplingDialog.getByRole("button", { name: "Apply sampling" }).click();

  await expect(page.samplingButton).toHaveText("Sampling (200)");
  expect(samplingRequests).toHaveLength(1);
  expect(samplingRequests[0]?.sql).toContain('WITH "__sc_sampling_base" AS');
  expect(samplingRequests[0]?.sql).toContain('ORDER BY HASH("defect_id", ?)');
});
