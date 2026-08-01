/**
 * Current SC training contract: one UI action submits training and then
 * prediction as a single workflow. The former independent training and
 * prediction cards no longer exist and must not be modeled by E2E tests.
 *
 * @live @slow — runs the real Prefect-backed workflow.
 */
import { expect, test } from "../../fixtures";
import { WaferTrainPredictPage } from "../../pages/sc/WaferTrainPredictPage";
import {
  cleanupTestArtifacts,
  countScPredictionsForTestIds,
  getLatestScInspection,
  setupScImportedAndAnnotated,
  waitForJobStatus,
  waitForWorkflowPredictionCompletion,
} from "../../seed";
import { E2E_TIMEOUTS } from "../../timeouts";

const LABELS = ["1", "2", "3", "4", "5"];
const ANNOTATE_COUNT = 100;

test.describe("Wafer Train & Predict @live @slow", () => {
  test.afterEach(async ({ testPrefix }) => {
    await cleanupTestArtifacts(testPrefix);
  });

  test("completes the unified workflow from the reclassify workspace", async ({
    page,
    liveAuth,
    seedClient,
    testPrefix,
  }) => {
    test.setTimeout(E2E_TIMEOUTS.test.scFullWorkflow);

    const setupStartedAt = Date.now();
    const inspection = await getLatestScInspection();
    const { datasetId, annotated, workflowTestIds } = await setupScImportedAndAnnotated(
      inspection.inspection_time,
      inspection.wafer_key,
      ANNOTATE_COUNT,
      LABELS,
      `${testPrefix}-wafer-train-predict`,
    );
    expect(annotated).toBe(ANNOTATE_COUNT);
    console.log(
      `[wafer-train-predict] 300k import + 100 annotations: ${Date.now() - setupStartedAt}ms`,
    );

    const workflowPage = new WaferTrainPredictPage(page);
    await workflowPage.goToWorkspace(datasetId);
    await workflowPage.selectFirstTrainer();
    // Keep this functional E2E production-shaped by importing the full 300k
    // inspection, but scope the CPU-only compatibility predictor to a bounded
    // set. Selecting Test IDs from the annotated rows guarantees the filtered
    // training input still contains multiple active labels. Full-dataset
    // prediction throughput is measured by the separate performance suite.
    await workflowPage.applyTestIdFilter(workflowTestIds);
    await expect(workflowPage.trainPredictButton).toBeEnabled({
      timeout: E2E_TIMEOUTS.operation.scDataLoad,
    });

    const workflowStartedAt = Date.now();
    const trainingJobId = await workflowPage.startFilteredTrainAndPredict();
    await expect(workflowPage.status).toContainText(/Workflow submitted|Training .*queued/);

    const trainingJob = await waitForJobStatus(trainingJobId, "completed", {
      timeout: E2E_TIMEOUTS.operation.training,
    });
    expect(trainingJob.dataset_id).toBe(datasetId);

    const predictionJob = await waitForWorkflowPredictionCompletion(datasetId, trainingJobId, {
      timeout: E2E_TIMEOUTS.operation.prediction,
    });
    expect(predictionJob.dataset_id).toBe(datasetId);
    expect(await countScPredictionsForTestIds(datasetId, workflowTestIds)).toBeGreaterThan(0);
    await expect(workflowPage.status).toContainText(/Workflow .* completed\./, {
      timeout: E2E_TIMEOUTS.operation.prediction,
    });
    console.log(`[wafer-train-predict] workflow completion: ${Date.now() - workflowStartedAt}ms`);
  });
});
