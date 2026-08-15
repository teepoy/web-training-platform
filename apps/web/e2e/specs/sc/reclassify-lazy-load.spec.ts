import path from "node:path";
import { test, expect } from "../../fixtures";
import { ReclassifyPagePom } from "../../pages/sc/ReclassifyPagePom";
import {
  mockScDefectIds,
  mockScPlotPoints,
  mockScViewSamplesPaged,
  mockScSamplesWithLabels,
  mockScDataset,
} from "../../mocks/handlers";

const DATASET_ID = "test-sc";

test.describe("SC Reclassify warmup and sidebar @mock", () => {
  test("renders current data shell without legacy warmup requests @mock", async ({
    authedPage,
  }) => {
    await authedPage.addInitScript(() => localStorage.setItem("ui_dark_mode", "true"));
    await mockScDataset(authedPage, DATASET_ID, {
      name: "Test SC Dataset",
      label_space: ["Scratch", "Clean"],
    });

    await mockScPlotPoints(authedPage, DATASET_ID, 1000);
    await mockScDefectIds(authedPage, DATASET_ID, 1000);
    await mockScViewSamplesPaged(authedPage, DATASET_ID, "patch_image_v1", 1000, 200);
    await mockScSamplesWithLabels(authedPage, DATASET_ID, 1000, 200);

    const requestEvents: string[] = [];
    authedPage.on("request", (req) => {
      const url = req.url();
      if (url.includes(`/api/v1/sc/datasets/${DATASET_ID}/plot-points/stream`)) {
        requestEvents.push("plot-points-stream");
      } else if (url.includes(`/api/v1/sc/datasets/${DATASET_ID}/plot-points`)) {
        requestEvents.push("plot-points-protobuf");
      } else if (url.includes(`/api/v1/sc/datasets/${DATASET_ID}/defect-ids.bin`)) {
        requestEvents.push("defect-ids");
      } else if (url.includes(`/api/v1/datasets/${DATASET_ID}/views/patch_image_v1/samples`)) {
        requestEvents.push("view-samples");
      }
    });

    const viewSampleRequests: Array<{ offset: number; url: string }> = [];
    authedPage.on("request", (req) => {
      if (req.url().includes(`/views/patch_image_v1/samples`)) {
        const url = new URL(req.url());
        const offset = parseInt(url.searchParams.get("offset") ?? "0", 10);
        viewSampleRequests.push({
          offset,
          url: req.url(),
        });
      }
    });

    const pom = new ReclassifyPagePom(authedPage);
    await pom.gotoReclassify(DATASET_ID);

    await expect(authedPage.getByText("Annotation").first()).toBeVisible();
    await expect(pom.headerSampleCount(0)).toBeVisible({ timeout: 5_000 });

    const datasetNameBox = await authedPage.getByTestId("sc-dataset-name").boundingBox();
    const globalFilterButton = authedPage.getByTestId("sc-global-filter-trigger");
    const globalFilterBox = await globalFilterButton.boundingBox();
    expect(datasetNameBox).not.toBeNull();
    expect(globalFilterBox).not.toBeNull();
    expect(globalFilterBox!.y).toBeGreaterThan(datasetNameBox!.y + datasetNameBox!.height);

    await globalFilterButton.click();
    await expect(authedPage.getByText("Global Filters", { exact: true })).toBeVisible();
    await authedPage.getByTestId("query-combinator-or").click();
    await authedPage.getByTestId("query-add-condition").click();
    await authedPage.locator(".sc-filter-rule__property-select .n-base-selection").click();
    const propertyOptions = authedPage.locator(".n-base-select-option");
    const defectIdOption = propertyOptions.filter({ hasText: /^Defect ID$/ });
    await expect(defectIdOption).toBeVisible();
    await defectIdOption.click();
    await expect(authedPage.locator(".sc-filter-rule__editor")).toBeVisible();
    await expect(authedPage.getByRole("button", { name: "Configure" })).toHaveCount(0);
    const itemBackground = await authedPage
      .locator(".query-builder__rule")
      .evaluate((element) => getComputedStyle(element).backgroundColor);
    expect(itemBackground).not.toBe("rgb(255, 255, 255)");

    expect(requestEvents).toEqual([]);
    expect(viewSampleRequests).toEqual([]);
  });

  test("reclassify sidebar exposes code/name labels and shortcut state @mock", async ({
    authedPage,
  }) => {
    await mockScDataset(authedPage, DATASET_ID, {
      name: "Test SC Dataset",
      label_space: [],
    });

    await mockScPlotPoints(authedPage, DATASET_ID, 24);
    await mockScDefectIds(authedPage, DATASET_ID, 24);
    await mockScViewSamplesPaged(authedPage, DATASET_ID, "patch_image_v1", 24, 24);
    await mockScSamplesWithLabels(authedPage, DATASET_ID, 24, 24);

    const pom = new ReclassifyPagePom(authedPage);
    await pom.gotoReclassify(DATASET_ID);

    await expect(authedPage.getByTestId("reclassify-code-row-0")).toContainText("Unclassified");
    await expect(authedPage.getByTestId("reclassify-code-row-60")).toContainText("Code 60");

    await expect(authedPage.getByTestId("reclassify-shortcut-button-60")).toHaveText("-");
  });

  test("Back always opens the active dataset detail page @mock", async ({ authedPage }) => {
    await mockScDataset(authedPage, DATASET_ID, {
      name: "Test SC Dataset",
      label_space: ["Scratch", "Clean"],
    });
    await mockScPlotPoints(authedPage, DATASET_ID, 24);
    await mockScDefectIds(authedPage, DATASET_ID, 24);
    await mockScViewSamplesPaged(authedPage, DATASET_ID, "patch_image_v1", 24, 24);
    await mockScSamplesWithLabels(authedPage, DATASET_ID, 24, 24);

    await authedPage.goto("/sc/handbook");

    const pom = new ReclassifyPagePom(authedPage);
    await pom.gotoReclassify(DATASET_ID);
    await authedPage.getByRole("button", { name: /Back$/ }).click();

    await expect(authedPage).toHaveURL(`/datasets/${DATASET_ID}`, { timeout: 2_000 });
  });
});
