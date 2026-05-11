import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { goToDatasets, goToDatasetDetail } from '../helpers/navigation';

const SEED_EMAIL = 'seed@example.com';
const SEED_PASSWORD = 'seed1234';
const SEEDED_DATASET = 'ImageNet-1K Mock';

test('navigate to seeded ImageNet dataset', async ({ page }) => {
  await loginViaUI(page, SEED_EMAIL, SEED_PASSWORD);

  await goToDatasets(page);

  // Find and click the seeded ImageNet dataset
  await expect(
    page.getByText(SEEDED_DATASET, { exact: true }).first(),
  ).toBeVisible({ timeout: 10000 });

  await goToDatasetDetail(page, SEEDED_DATASET);

  // Verify we're on the dataset detail page
  await expect(page).toHaveURL(/\/datasets\//);

  // Verify "Open Workflow" button is visible
  await expect(
    page.getByRole('button', { name: 'Open Workflow' }),
  ).toBeVisible({ timeout: 5000 });

  // Navigate to Samples tab and verify sample browser is visible
  await expect(page.locator('.ds-samples-layout')).toBeVisible({ timeout: 10000 });
});

test('open workflow and launch predictions', async ({ page }) => {
  await loginViaUI(page, SEED_EMAIL, SEED_PASSWORD);

  await goToDatasets(page);

  // Open the seeded ImageNet dataset detail
  await goToDatasetDetail(page, SEEDED_DATASET);

  // Click "Open Workflow" to enter the classify workflow
  await page.getByRole('button', { name: 'Open Workflow' }).click();
  await expect(page).toHaveURL(/\/datasets\/.+\/classify/);
  await expect(page.locator('.classify-view')).toBeVisible({ timeout: 10000 });

  // Verify the Prediction Review card is visible
  const predictionCard = page.locator('.n-card').filter({ hasText: 'Prediction Review' });
  await expect(predictionCard).toBeVisible({ timeout: 5000 });

  // Verify the "Run Predictions" button exists but is disabled (no model selected yet)
  const runButton = predictionCard.getByRole('button', { name: 'Run Predictions' });
  await expect(runButton).toBeVisible();

  // Select a model from the dropdown
  const modelSelect = predictionCard.locator('.n-base-selection').filter({ hasText: 'Select model' });
  await modelSelect.first().click();

  // Wait for the select dropdown to appear and pick the first model option
  const firstOption = page.locator('.n-base-select-option').first();
  await expect(firstOption).toBeVisible({ timeout: 5000 });
  await firstOption.click();

  // The "Run Predictions" button should now be enabled
  await expect(runButton).not.toBeDisabled({ timeout: 3000 });

  // Click "Run Predictions" to submit a prediction job
  await runButton.click();

  // Verify a success toast appears indicating the prediction job was submitted
  await expect(
    page.locator('.n-message').filter({ hasText: 'Prediction job submitted' }),
  ).toBeVisible({ timeout: 30000 });
});
