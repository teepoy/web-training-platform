/**
 * Chained smoke: full wafer inspection E2E workflow through UI.
 *
 * Runs import → annotate → train → predict → export sequentially through
 * the real frontend. For nightly smoke, not default CI.
 *
 * @live @smoke — all phases chained; long timeout.
 */
import { test, expect } from '../../fixtures';
import { WaferImportPage } from '../../pages/sc/WaferImportPage';
import { WaferTrainingPage } from '../../pages/sc/WaferTrainingPage';
import { WaferPredictExportPage } from '../../pages/sc/WaferPredictExportPage';
import { waitForToast } from '../../helpers/navigation';
import { waitForJobStatus } from '../../seed/training';
import {
  listModelsApiV1ModelsGet,
  getPredictionJobApiV1PredictionJobsJobIdGet,
  listPredictionJobsApiV1PredictionJobsGet,
} from '@/generated/orval/endpoints/api';
import type { ModelResponse, PredictionJobResponse } from '@/generated/orval/models';

const LABELS = ['Scratch', 'Particle', 'Pattern Defect', 'Residue', 'Crack'];
const ANNOTATE_COUNT = 100;
const IMPORT_TIMEOUT = 180_000;
const TRAIN_TIMEOUT = 600_000;
const PREDICT_TIMEOUT = 900_000;

function hoursAgo(hours: number): string {
  const d = new Date(Date.now() - hours * 3600_000);
  return d.toISOString().slice(0, 16).replace('T', ' ') + ':00';
}

function nowFormatted(): string {
  return new Date().toISOString().slice(0, 16).replace('T', ' ') + ':00';
}

async function findModelForDataset(datasetId: string): Promise<string> {
  const res = await listModelsApiV1ModelsGet({ dataset_id: datasetId });
  const models = res.data as ModelResponse[];
  if (!Array.isArray(models) || models.length === 0) {
    throw new Error(`No models found for dataset ${datasetId}`);
  }
  return models[0].id!;
}

async function waitForPredictionComplete(
  jobId: string,
  timeoutMs = 900_000,
): Promise<PredictionJobResponse> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const res = await getPredictionJobApiV1PredictionJobsJobIdGet(jobId);
    const job = res.data as PredictionJobResponse;
    const status = String(job.status || '').toLowerCase();
    if (['completed', 'failed', 'cancelled'].includes(status)) {
      return job;
    }
    await new Promise((r) => setTimeout(r, 3000));
  }
  throw new Error(`Prediction job ${jobId} did not complete within ${timeoutMs}ms`);
}

test.describe('Wafer Smoke E2E Chained @live @smoke', () => {
  test('full wafer workflow: import → annotate → train → predict → export', async ({
    page,
    liveAuth,
    seedClient,
    testPrefix,
  }) => {
    test.setTimeout(1_800_000);

    const importPage = new WaferImportPage(page);
    const trainingPage = new WaferTrainingPage(page);
    const predictExportPage = new WaferPredictExportPage(page);

    // ════════════════════════════════════════════════════════════════
    // Phase 1: Import via UI
    // ════════════════════════════════════════════════════════════════
    const datasetName = `WaferSmoke-${testPrefix}`;

    await importPage.goToScPreview();

    const startTime = hoursAgo(48);
    const endTime = nowFormatted();
    await importPage.fillTimeRange(startTime, endTime);
    await importPage.clickSearch();
    await importPage.waitForTableRows();

    await importPage.openFirstInspection();
    await importPage.clickImportAsDataset();
    await importPage.waitForImportModal();

    await importPage.fillDatasetName(datasetName);
    await importPage.selectStorageModeSparseShard();
    await importPage.clickStartImport();

    const classifyUrl = await importPage.waitForImportCompletion(IMPORT_TIMEOUT);
    const datasetId = importPage.extractDatasetId(classifyUrl)!;
    expect(datasetId).toBeTruthy();

    await expect(page.locator('.classify-page')).toBeVisible({ timeout: 10_000 });

    // ════════════════════════════════════════════════════════════════
    // Phase 2: Annotate via browser API (same as monolith pattern)
    // ════════════════════════════════════════════════════════════════
    const annotResult = await page.evaluate(
      async ({ datasetId, labels, count, token }) => {
        const headers = {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        };

        const allItems: Array<{ defect_id: string; sample_id: string }> = [];
        let offset = 0;
        const limit = 200;
        while (true) {
          const resp = await fetch(
            `/api/v1/datasets/${datasetId}/views/patch_image_v1/samples?offset=${offset}&limit=${limit}`,
            { headers },
          );
          if (!resp.ok) throw new Error(`List samples failed: ${resp.status}`);
          const body = await resp.json();
          const items = body.items || [];
          if (items.length === 0) break;
          allItems.push(...items);
          offset += limit;
          if (offset >= (body.total || 0)) break;
        }

        const toAnnotate = Math.min(count, allItems.length);
        const shuffled = [...allItems].sort(() => Math.random() - 0.5);
        const annotations = shuffled.slice(0, toAnnotate).map((item) => ({
          defect_id: item.defect_id,
          label: labels[Math.floor(Math.random() * labels.length)],
        }));

        const bulkResp = await fetch(
          `/api/v1/datasets/${datasetId}/annotations/bulk-sc`,
          {
            method: 'POST',
            headers,
            body: JSON.stringify({ annotations }),
          },
        );
        if (!bulkResp.ok)
          throw new Error(`Bulk annotate failed: ${bulkResp.status}`);
        const result = await bulkResp.json();

        return {
          annotated: result.created || annotations.length,
          totalSamples: allItems.length,
        };
      },
      {
        datasetId,
        labels: LABELS,
        count: ANNOTATE_COUNT,
        token: liveAuth.token,
      },
    );

    expect(annotResult.annotated).toBeGreaterThan(0);

    // ════════════════════════════════════════════════════════════════
    // Phase 3: Train via UI
    // ════════════════════════════════════════════════════════════════
    await trainingPage.waitForTrainingCard();
    await trainingPage.selectFirstTrainer();
    await trainingPage.clickStartTraining();
    await waitForToast(page, 'Training job started');

    const jobIdFromUi = await trainingPage.getActiveJobId();
    if (!jobIdFromUi) throw new Error('Could not resolve training job ID');

    const trainResult = await waitForJobStatus(jobIdFromUi, 'completed', {
      timeout: TRAIN_TIMEOUT,
    });
    expect(trainResult.status).toBe('completed');

    // ════════════════════════════════════════════════════════════════
    // Phase 4: Predict + Export via UI
    // ════════════════════════════════════════════════════════════════
    const modelId = await findModelForDataset(datasetId);

    await predictExportPage.waitForPredictionCard();
    await predictExportPage.selectModel(modelId);
    await predictExportPage.clickRunPredictions();
    await waitForToast(page, 'Prediction job submitted');

    let predJobId = await predictExportPage.getActivePredictionJobId();
    if (!predJobId) {
      const jobsRes = await listPredictionJobsApiV1PredictionJobsGet();
      const jobs = (jobsRes.data as PredictionJobResponse[]) || [];
      const recentJob = (Array.isArray(jobs) ? jobs : [])
        .filter((j) => j.dataset_id === datasetId)
        .sort((a, b) =>
          (b.created_at || '').localeCompare(a.created_at || ''),
        )[0];
      if (recentJob) predJobId = recentJob.id!;
    }

    if (predJobId) {
      const predResult = await waitForPredictionComplete(
        predJobId,
        PREDICT_TIMEOUT,
      );
      expect(String(predResult.status || '').toLowerCase()).toBe('completed');
    } else {
      await waitForToast(page, 'predictions ready for review');
    }

    // Export
    await predictExportPage.goToDatasetView(datasetId);
    await predictExportPage.clickExportTab();
    await predictExportPage.clickExportDataset();
    await predictExportPage.waitForExportModal();

    await predictExportPage.clickPersistExportCard();
    await predictExportPage.clickPersistExportAction();
    await predictExportPage.waitForExportSuccess();

    const alertText = await predictExportPage.exportSuccessAlert.innerText();
    expect(alertText).toContain('Export persisted:');

    await predictExportPage.clickDone();
  });
});
