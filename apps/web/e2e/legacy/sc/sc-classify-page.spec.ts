import { test, expect } from "../../fixtures";
import { makeSamples } from "../../mocks/factories";

const datasetId = "sc-classify-1";

test("SC classify page renders blink table and annotation sidebar @legacy", async ({
  authedPage,
  apiMocks,
}) => {
  await apiMocks.sc.mockScDataset(datasetId, {
    name: "SC Wafer Dataset",
    label_space: ["Scratch", "Particle", "Pattern Defect"],
  });
  await apiMocks.sc.mockScViewSamples(datasetId, "patch_image_v1", { total: 2 });
  await apiMocks.datasets.mockListSamples(datasetId, makeSamples(datasetId, 2));

  await authedPage.goto(`/datasets/${datasetId}/sc/classify`);
  await authedPage.waitForLoadState("domcontentloaded");

  await expect(authedPage.getByText("SC Wafer Dataset")).toBeVisible();
  await expect(authedPage.getByText("Annotation")).toBeVisible();
  await expect(authedPage.getByRole("button", { name: /Submit/ })).toBeVisible();
});
