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
});
