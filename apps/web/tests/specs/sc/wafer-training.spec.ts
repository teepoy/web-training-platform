/**
 * Phase 3: SC wafer training workflow.
 *
 * Uses seedClient to import an SC dataset via API, bulk-annotate samples,
 * then interacts with the training UI on the classify page to start and
 * monitor a training job.
 *
 * @live @slow — training may take several minutes.
 */
import { test, expect } from '../../fixtures';
import { WaferTrainingPage } from '../../pages/sc/WaferTrainingPage';
import { waitForToast } from '../../helpers/navigation';
import { setupScImportedAndAnnotated } from '../../seed/sc';
import { waitForJobStatus } from '../../seed/training';

const LABELS = ['Scratch', 'Particle', 'Pattern Defect', 'Residue', 'Crack'];
const ANNOTATE_COUNT = 100;
const TRAIN_TIMEOUT = 600_000;

function nowFormatted(): string {
  return new Date().toISOString().slice(0, 16).replace('T', ' ') + ':00';
}

test.describe('Wafer Training @live @slow', () => {
  test('start and complete wafer training from classify UI', async ({
    page,
    liveAuth,
    seedClient,
    testPrefix,
  }) => {
    test.setTimeout(900_000);

    // Seed: import + annotate via API
    const { datasetId } = await setupScImportedAndAnnotated(
      nowFormatted(),
      1,
      ANNOTATE_COUNT,
      LABELS,
    );

    const trainingPage = new WaferTrainingPage(page);
    await trainingPage.goToClassify(datasetId);
    await trainingPage.waitForTrainingCard();

    // Select trainer
    await trainingPage.selectFirstTrainer();

    // Start training
    await trainingPage.clickStartTraining();
    await waitForToast(page, 'Training job started');

    // Resolve job ID
    const jobIdFromUi = await trainingPage.getActiveJobId();
    if (!jobIdFromUi) throw new Error('Could not resolve training job ID from UI');

    // Wait for training to complete
    const trainResult = await waitForJobStatus(jobIdFromUi, 'completed', {
      timeout: TRAIN_TIMEOUT,
    });
    expect(trainResult.status).toBe('completed');
  });
});
