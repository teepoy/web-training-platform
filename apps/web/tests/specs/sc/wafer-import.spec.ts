/**
 * Phase 1: SC wafer import workflow.
 *
 * Searches for wafer inspections on the SC preview page, opens the import
 * modal from an inspection row, fills the form, submits, and verifies the
 * dataset appears on the classify page.
 *
 * @live @smoke — imports always run against a real backend; keep fast.
 */
import { test, expect } from '../../fixtures';
import { WaferImportPage } from '../../pages/sc/WaferImportPage';

const DATASET_PREFIX = 'WaferImport';

function hoursAgo(hours: number): string {
  const d = new Date(Date.now() - hours * 3600_000);
  return d.toISOString().slice(0, 16).replace('T', ' ') + ':00';
}

function nowFormatted(): string {
  return new Date().toISOString().slice(0, 16).replace('T', ' ') + ':00';
}

test.describe('Wafer Import @live @smoke', () => {
  test('import wafer dataset from SC preview', async ({
    page,
    liveAuth,
    seedClient,
    testPrefix,
  }) => {
    test.setTimeout(240_000);

    const waferPage = new WaferImportPage(page);
    const datasetName = `${DATASET_PREFIX}-${testPrefix}`;

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

    // Open import modal
    await waferPage.clickImportAsDataset();
    await waferPage.waitForImportModal();

    // Fill import form
    await waferPage.fillDatasetName(datasetName);
    await waferPage.selectStorageModeSparseShard();

    // Submit import
    await waferPage.clickStartImport();

    // Wait for completion → redirect to classify
    const classifyUrl = await waferPage.waitForImportCompletion(180_000);
    const datasetId = waferPage.extractDatasetId(classifyUrl);
    expect(datasetId).toBeTruthy();

    // Verify classify page loaded
    await expect(page.locator('.classify-page')).toBeVisible({ timeout: 10_000 });
  });
});
