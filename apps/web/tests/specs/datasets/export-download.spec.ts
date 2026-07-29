import { test, expect } from "../../fixtures";
import { DatasetDetailPage } from "../../pages/datasets/DatasetDetailPage";

const datasetId = "dataset-export-1";

test("Export results show downloadable link after persist @legacy", async ({
  authedPage,
  apiMocks,
}) => {
  const page = new DatasetDetailPage(authedPage);

  await apiMocks.datasets.mockGetDataset(datasetId);
  await apiMocks.datasets.mockExportDownload();

  await authedPage.route(`**/api/v1/exports/${datasetId}/persist`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        uri: "s3://bucket/exports/dataset-export-1.json",
      }),
    });
  });

  await page.gotoDetail(datasetId);
  await page.waitForLoaded();

  await page.gotoExportTab();

  await authedPage.getByText("Persist Export").click();

  await expect(authedPage.getByRole("button", { name: "Persist Export" })).toBeVisible({
    timeout: 5_000,
  });

  await authedPage.getByRole("button", { name: "Persist Export" }).click();

  const downloadLink = authedPage.getByRole("link", { name: "Download Export" });
  await expect(downloadLink).toBeVisible({ timeout: 10_000 });

  const href = await downloadLink.getAttribute("href");
  expect(href).toContain("/api/v1/download?uri=");
  expect(href).toContain("token=");
});
