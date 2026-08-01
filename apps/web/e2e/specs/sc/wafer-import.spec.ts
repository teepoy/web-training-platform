/**
 * Phase 1: SC wafer import workflow.
 *
 * Searches for wafer inspections on the SC preview page, opens the import
 * inspection page, starts reclassification, and verifies the dataset appears
 * on the classify page.
 *
 * @live @slow — the aligned development fixture contains 300,000 defects.
 */
import { test, expect } from "../../fixtures";
import { WaferImportPage } from "../../pages/sc/WaferImportPage";
import { deleteDataset } from "../../seed";
import { E2E_TIMEOUTS } from "../../timeouts";

function hoursAgo(hours: number): string {
  const d = new Date(Date.now() - hours * 3600_000);
  return d.toISOString().slice(0, 16).replace("T", " ") + ":00";
}

function nowFormatted(): string {
  return new Date().toISOString().slice(0, 16).replace("T", " ") + ":00";
}

test.describe("Wafer Import @live @slow", () => {
  test("import wafer dataset from SC preview", async ({ page, liveAuth, seedClient }) => {
    test.setTimeout(E2E_TIMEOUTS.test.scImport);
    let datasetId: string | null = null;

    try {
      const waferPage = new WaferImportPage(page);
      await waferPage.goToScPreview();

      // Search for recent inspections
      const startTime = hoursAgo(48);
      const endTime = nowFormatted();
      await waferPage.fillTimeRange(startTime, endTime);
      await waferPage.clickSearch();

      // Wait for table rows
      await waferPage.waitForTableRows();

      // Open first inspection
      await waferPage.openFirstInspection();

      // Import with the inspection page's fixed sparse-shard configuration.
      await waferPage.clickReclassify();

      // Wait for completion → redirect to classify
      const coldLoadStartedAt = Date.now();
      const classifyUrl = await waferPage.waitForImportCompletion();
      datasetId = waferPage.extractDatasetId(classifyUrl);
      expect(datasetId).toBeTruthy();

      // Verify the current reclassify workspace and its streamed data loaded.
      await expect(page.locator(".sc-classify-page")).toBeVisible();
      await page
        .locator(".sbt-sample-block")
        .first()
        .waitFor({ timeout: E2E_TIMEOUTS.operation.scDataLoad });
      console.log(`[wafer-import] 300k cold workspace load: ${Date.now() - coldLoadStartedAt}ms`);
    } finally {
      if (datasetId) await deleteDataset(datasetId).catch(() => undefined);
    }
  });
});
