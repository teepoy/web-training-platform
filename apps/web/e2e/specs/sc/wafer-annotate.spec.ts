/**
 * Phase 2: SC wafer annotation workflow.
 *
 * Uses seedClient to import an SC dataset via API, then verifies the
 * classify annotation UI loads with sample items and annotation controls.
 *
 * @live — independent; sets up import state via API.
 */
import { test, expect } from "../../fixtures";
import { WaferAnnotatePage } from "../../pages/sc/WaferAnnotatePage";
import { getLatestScInspection, startScImport, waitForScImportByDatasetName } from "../../seed/sc";
import { cleanupTestArtifacts } from "../../seed";
import type { ScImportRequest } from "@/generated/orval/models";
import { E2E_TIMEOUTS } from "../../timeouts";

test.describe("Wafer Annotation @live", () => {
  test.afterEach(async ({ testPrefix }) => {
    await cleanupTestArtifacts(testPrefix);
  });

  test("annotation UI loads after API import", async ({
    page,
    liveAuth,
    seedClient,
    testPrefix,
  }) => {
    test.setTimeout(E2E_TIMEOUTS.test.scAnnotation);

    // Seed: import SC dataset via API
    const inspection = await getLatestScInspection();
    const datasetName = `${testPrefix}-wafer-annotate`;
    const importReq: ScImportRequest = {
      source_inspection_time: inspection.inspection_time,
      source_wafer_key: inspection.wafer_key,
      dataset_name: datasetName,
      storage_mode: "file_shard_sparse",
    };
    await startScImport(importReq);
    const datasetId = await waitForScImportByDatasetName(datasetName);

    const annotatePage = new WaferAnnotatePage(page);

    const coldLoadStartedAt = Date.now();
    await annotatePage.goToClassify(datasetId);

    await expect(annotatePage.classifyPage).toBeVisible();
    await annotatePage.waitForSamples();
    console.log(`[wafer-annotate] 300k cold workspace load: ${Date.now() - coldLoadStartedAt}ms`);

    // Verify sample browser has items
    const itemCount = await annotatePage.sampleBrowserItems.count();
    expect(itemCount).toBeGreaterThan(0);

    await expect(annotatePage.mapPanel).toBeVisible();
    await expect(annotatePage.sampleTable).toBeVisible();
    await expect(annotatePage.annotationGrid).toBeVisible();
  });
});
