import { test, expect } from "../../fixtures";

const datasetId = "sc-classify-1";

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
