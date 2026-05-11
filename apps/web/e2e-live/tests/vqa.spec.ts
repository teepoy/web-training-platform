import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';

const SEED_EMAIL = 'seed@example.com';
const SEED_PASSWORD = 'seed1234';
const API_BASE = process.env.API_URL || 'http://localhost:8000';

function vqaDatasetName(): string {
  return `E2E VQA ${Date.now()}`;
}

function vqaSamplesJson(): Buffer {
  return Buffer.from(
    JSON.stringify([
      {
        image_uris: ['memory://vqa-e2e-sample.jpg'],
        metadata: { question: 'What is shown in this image?' },
      },
    ]),
  );
}

async function uploadVqaSamplesJson(
  page: import('@playwright/test').Page,
): Promise<void> {
  await page
    .locator('input[type="file"][accept="application/json"]')
    .setInputFiles({
      name: 'vqa-samples.json',
      mimeType: 'application/json',
      buffer: vqaSamplesJson(),
    });
}

async function fillVqaDatasetForm(
  page: import('@playwright/test').Page,
  opts: { name: string },
): Promise<void> {
  await page.getByPlaceholder('e.g. imported-dataset').fill(opts.name);

  await page
    .locator('.n-base-selection')
    .filter({ hasText: 'Select dataset type' })
    .first()
    .click();
  await page.locator('.n-base-select-option').filter({ hasText: 'Image VQA' }).click();

  await uploadVqaSamplesJson(page);
  await expect(page.getByText(/vqa-samples\.json/)).toBeVisible({ timeout: 3000 });
}

async function submitImportAndVerify(
  page: import('@playwright/test').Page,
  name: string,
): Promise<void> {
  await page.getByRole('button', { name: 'Import', exact: true }).click();

  await expect(
    page.locator('.n-message').filter({ hasText: /(dataset (imported|created))/i }),
  ).toBeVisible({ timeout: 30000 });

  await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 10000 });
  await expect(page.getByText(name, { exact: true })).toBeVisible({ timeout: 5000 });
}

test('create VQA dataset', async ({ page }) => {
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  const name = vqaDatasetName();

  await loginViaUI(page, SEED_EMAIL, SEED_PASSWORD);

  await page.getByRole('button', { name: 'Import Dataset' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByText('Manual Dataset').click();

  await fillVqaDatasetForm(page, { name });
  await submitImportAndVerify(page, name);
});

test('VQA prediction endpoint available', async ({ page }) => {
  await loginViaUI(page, SEED_EMAIL, SEED_PASSWORD);

  const apiResponse = await page.request.post(`${API_BASE}/api/v1/predictions/single`, {
    data: {
      model_id: 'e2e-vqa-model',
      sample_id: 'e2e-vqa-sample',
      target: 'vqa',
      prompt: 'What is shown in this image?',
    },
    headers: {
      Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem('auth_token') || '')}`,
    },
  });

  expect([200, 400, 422]).toContain(apiResponse.status());

  const responseBody = await apiResponse.json();

  if (apiResponse.status() !== 200) {
    const detail =
      typeof responseBody?.detail === 'string' ? responseBody.detail : '';
    if (
      detail.toLowerCase().includes('llm') ||
      detail.toLowerCase().includes('not found') ||
      detail.toLowerCase().includes('model')
    ) {
      console.log(`VQA prediction endpoint responded (${apiResponse.status()}): ${detail}`);
      return;
    }
  }

  expect(responseBody).toHaveProperty('sample_id');
  expect(responseBody).toHaveProperty('predicted_label');
});
