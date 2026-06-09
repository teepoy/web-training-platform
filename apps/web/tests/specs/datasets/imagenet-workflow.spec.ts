import { test, expect } from '../../fixtures';
import { ClassifyWorkflowPage } from '../../pages/classify/ClassifyWorkflowPage';

const SEEDED_DATASET = 'ImageNet-1K Mock';

test('navigate to seeded ImageNet dataset @live @slow', async ({ page, liveAuth }) => {
  await page.addInitScript((token) => {
    localStorage.setItem('auth_token', token);
  }, liveAuth.token);

  await page.goto('/datasets');
  await page.waitForSelector('.n-data-table');

  await expect(
    page.getByText(SEEDED_DATASET, { exact: true }).first(),
  ).toBeVisible({ timeout: 10_000 });

  await page.getByText(SEEDED_DATASET, { exact: true }).first().click();

  await expect(page).toHaveURL(/\/datasets\//);

  await expect(
    page.getByRole('button', { name: 'Open Workflow' }),
  ).toBeVisible({ timeout: 5_000 });

  await expect(page.locator('.ds-samples-layout')).toBeVisible({ timeout: 10_000 });
});

test('open workflow and launch predictions @live @slow', async ({ page, liveAuth }) => {
  await page.addInitScript((token) => {
    localStorage.setItem('auth_token', token);
  }, liveAuth.token);

  await page.goto('/datasets');
  await page.waitForSelector('.n-data-table');

  await page.getByText(SEEDED_DATASET, { exact: true }).first().click();
  await expect(page).toHaveURL(/\/datasets\//);

  await page.getByRole('button', { name: 'Open Workflow' }).click();
  await expect(page).toHaveURL(/\/datasets\/.+\/classify/);
  await expect(page.locator('.classify-view')).toBeVisible({ timeout: 10_000 });

  const workflowPage = new ClassifyWorkflowPage(page);

  const predictionCard = page.locator('.n-card').filter({ hasText: 'Prediction Review' });
  await expect(predictionCard).toBeVisible({ timeout: 5_000 });

  const runButton = workflowPage.getRunPredictionsButton();
  await expect(runButton).toBeVisible();

  const modelSelect = predictionCard.locator('.n-base-selection').filter({ hasText: 'Select model' });
  await modelSelect.first().click();

  const firstOption = page.locator('.n-base-select-option').first();
  await expect(firstOption).toBeVisible({ timeout: 5_000 });
  await firstOption.click();

  await expect(runButton).not.toBeDisabled({ timeout: 3_000 });

  await workflowPage.clickRunPredictions();

  await expect(
    page.locator('.n-message').filter({ hasText: 'Prediction job submitted' }),
  ).toBeVisible({ timeout: 30_000 });
});
