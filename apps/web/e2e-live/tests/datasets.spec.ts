import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { goToDatasets, goToDatasetDetail } from '../helpers/navigation';

const SEED_EMAIL = 'seed@example.com';
const SEED_PASSWORD = 'seed1234';

function datasetName(prefix = 'E2E Dataset'): string {
  return `${prefix} ${Date.now()}`;
}

function samplesJsonBuffer(): Buffer {
  return Buffer.from(
    JSON.stringify([
      {
        image_uris: ['memory://e2e-test-sample.jpg'],
        metadata: { source: 'e2e-live' },
        label: null,
      },
    ]),
  );
}

async function uploadSamplesJson(page: import('@playwright/test').Page): Promise<void> {
  await page
    .locator('input[type="file"][accept="application/json"]')
    .setInputFiles({
      name: 'samples.json',
      mimeType: 'application/json',
      buffer: samplesJsonBuffer(),
    });
}

async function fillDatasetForm(
  page: import('@playwright/test').Page,
  opts: { name: string; labels: string[] },
): Promise<void> {
  await page.getByPlaceholder('e.g. imported-dataset').fill(opts.name);

  await page.getByPlaceholder('Select dataset type').click();
  await page.getByText('Image Classification', { exact: true }).click();

  await expect(page.locator('.n-dynamic-tags')).toBeVisible({ timeout: 5000 });

  for (const label of opts.labels) {
    await page.locator('.n-dynamic-tags').click();
    await page.keyboard.type(label);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(200);
  }

  await uploadSamplesJson(page);
  await expect(page.getByText(/samples\.json/)).toBeVisible({ timeout: 3000 });
}

async function submitImportAndVerify(
  page: import('@playwright/test').Page,
  name: string,
): Promise<void> {
  await page.getByRole('button', { name: 'Import', exact: true }).click();

  await expect(page.getByText(name, { exact: true })).toBeVisible({
    timeout: 15000,
  });
}

test('create dataset with labels', async ({ page }) => {
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  const name = datasetName();

  await loginViaUI(page, SEED_EMAIL, SEED_PASSWORD);

  await page.getByRole('button', { name: 'Import Dataset' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByText('Import from JSON').click();

  await fillDatasetForm(page, { name, labels: ['cat', 'dog'] });
  await submitImportAndVerify(page, name);
});

test('view dataset detail', async ({ page }) => {
  await goToDatasets(page);

  const name = datasetName('E2E Detail');

  await page.getByRole('button', { name: 'Import Dataset' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByText('Import from JSON').click();
  await fillDatasetForm(page, { name, labels: ['cat', 'dog'] });
  await submitImportAndVerify(page, name);

  await goToDatasetDetail(page, name);

  await expect(
    page.locator('.n-tabs .n-tabs-tab').filter({ hasText: 'Samples' }),
  ).toBeVisible();

  await expect(page.locator('.ds-samples-layout')).toBeVisible({ timeout: 10000 });

  const lsLink = page.getByText(/Label Studio Project #/);
  if (await lsLink.isVisible({ timeout: 3000 }).catch(() => false)) {
    await expect(lsLink).toBeVisible();
  }
});

test('add labels to dataset', async ({ page }) => {
  await goToDatasets(page);

  const name = datasetName('E2E Labels');

  await page.getByRole('button', { name: 'Import Dataset' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByText('Import from JSON').click();
  await fillDatasetForm(page, { name, labels: ['cat', 'dog'] });
  await submitImportAndVerify(page, name);

  await goToDatasetDetail(page, name);

  await page.getByRole('button', { name: 'Open Workflow' }).click();
  await expect(page).toHaveURL(/\/datasets\/.+\/classify/);
  await expect(page.locator('.classify-view')).toBeVisible({ timeout: 10000 });

  const addLabelButton = page.locator('.classify-label-add');
  await expect(addLabelButton).toBeVisible({ timeout: 5000 });
  await addLabelButton.click();

  await expect(page.getByText('Add New Label')).toBeVisible({ timeout: 3000 });

  await page.getByPlaceholder('Enter label name').fill('bird');
  await page.getByRole('button', { name: 'Add', exact: true }).click();

  await expect(page.locator('.n-message', { hasText: /Added label/ })).toBeVisible({
    timeout: 10000,
  });

  await expect(
    page.locator('.classify-label-item').filter({ hasText: 'bird' }),
  ).toBeVisible({ timeout: 5000 });
});
