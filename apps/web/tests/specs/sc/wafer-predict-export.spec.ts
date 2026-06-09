/**
 * Phase 4: SC wafer prediction + export workflow.
 *
 * Uses seedClient to import, annotate, and train an SC dataset via API,
 * then runs predictions from the classify UI, waits for completion,
 * and exports the dataset with predictions via the export UI.
 *
 * @live — independent; full setup via API.
 */
import { test, expect } from '../../fixtures';
import { WaferPredictExportPage } from '../../pages/sc/WaferPredictExportPage';
import { waitForToast } from '../../helpers/navigation';
import { setupScImportedAndAnnotated } from '../../seed/sc';
import {
  startTrainingJob,
  waitForJobStatus,
  listTrainers,
} from '../../seed/training';
import {
  listModelsApiV1ModelsGet,
  listPredictionJobsApiV1PredictionJobsGet,
  getPredictionJobApiV1PredictionJobsJobIdGet,
} from '@/generated/orval/endpoints/api';
import type {
  CreateTrainingJobRequest,
  ModelResponse,
  PredictionJobResponse,
} from '@/generated/orval/models';

const LABELS = ['Scratch', 'Particle', 'Pattern Defect', 'Residue', 'Crack'];
const ANNOTATE_COUNT = 100;
const TRAIN_TIMEOUT = 600_000;
const PREDICT_TIMEOUT = 900_000;

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

test.describe('Wafer Predict + Export @live', () => {
  test('run predictions and export dataset via UI', async ({
    page,
    liveAuth,
    seedClient,
    testPrefix,
  }) => {
    test.setTimeout(1_800_000);

    // ── Seed: import + annotate via API ──
    const { datasetId } = await setupScImportedAndAnnotated(
      nowFormatted(),
      1,
      ANNOTATE_COUNT,
      LABELS,
    );

    // ── Seed: train via API ──
    const trainers = await listTrainers();
    if (trainers.length === 0) {
      throw new Error('No trainers available');
    }
    const trainerId = String(trainers[0].trainer_id ?? trainers[0].id ?? '');

    const trainReq: CreateTrainingJobRequest = {
      dataset_id: datasetId,
      trainer_id: trainerId,
    };
    const trainJob = await startTrainingJob(trainReq);
    const trainJobId = trainJob.id!;

    await waitForJobStatus(trainJobId, 'completed', { timeout: TRAIN_TIMEOUT });

    // ── Seed: find model ──
    const modelId = await findModelForDataset(datasetId);

    // ── Test: predict via UI ──
    const predictPage = new WaferPredictExportPage(page);
    await predictPage.goToClassify(datasetId);
    await predictPage.waitForPredictionCard();

    await predictPage.selectModel(modelId);
    await predictPage.clickRunPredictions();
    await waitForToast(page, 'Prediction job submitted');

    // Resolve prediction job ID
    let predJobId = await predictPage.getActivePredictionJobId();
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
      const predResult = await waitForPredictionComplete(predJobId, PREDICT_TIMEOUT);
      expect(String(predResult.status || '').toLowerCase()).toBe('completed');
    } else {
      await waitForToast(page, 'predictions ready for review');
    }

    // ── Test: export via UI ──
    await predictPage.goToDatasetView(datasetId);
    await predictPage.clickExportTab();
    await predictPage.clickExportDataset();
    await predictPage.waitForExportModal();

    await predictPage.clickPersistExportCard();
    await predictPage.clickPersistExportAction();
    await predictPage.waitForExportSuccess();

    const alertText = await predictPage.exportSuccessAlert.innerText();
    expect(alertText).toContain('Export persisted:');

    await predictPage.clickDone();
  });
});
