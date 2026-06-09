import { test, expect } from '../../fixtures';
import { cleanupTestArtifacts } from '../../seed';

test('create VQA dataset @live', async ({ page, liveAuth, seedClient: _sc, testPrefix }) => {
  await page.addInitScript((token) => {
    localStorage.setItem('auth_token', token);
  }, liveAuth.token);

  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  const name = `${testPrefix}-vqa`;

  try {
    await page.goto('/datasets');
    await page.waitForSelector('.n-data-table');

    await page.getByRole('button', { name: 'Import Dataset' }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.getByText('Manual Dataset').click();

    await page.getByPlaceholder('e.g. imported-dataset').fill(name);

    await page
      .locator('.n-base-selection')
      .filter({ hasText: 'Select dataset type' })
      .first()
      .click();
    await page.locator('.n-base-select-option').filter({ hasText: 'Image VQA' }).click();

    await page
      .locator('input[type="file"][accept="application/json"]')
      .setInputFiles({
        name: 'vqa-samples.json',
        mimeType: 'application/json',
        buffer: Buffer.from(
          JSON.stringify([
            {
              image_uris: ['memory://vqa-e2e-sample.jpg'],
              metadata: { question: 'What is shown in this image?' },
            },
          ]),
        ),
      });
    await expect(page.getByText(/vqa-samples\.json/)).toBeVisible({ timeout: 3_000 });

    await page.getByRole('button', { name: 'Import', exact: true }).click();

    await expect(
      page.locator('.n-message').filter({ hasText: /(dataset (imported|created))/i }),
    ).toBeVisible({ timeout: 30_000 });

    await expect(page.getByRole('dialog')).not.toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(name, { exact: true })).toBeVisible({ timeout: 5_000 });
  } finally {
    await cleanupTestArtifacts(testPrefix);
  }
});

test('VQA prediction endpoint available @live', async ({ page, liveAuth }) => {
  const API_BASE = process.env.API_URL || 'http://localhost:8000';

  const apiResponse = await page.request.post(`${API_BASE}/api/v1/predictions/single`, {
    data: {
      model_id: 'e2e-vqa-model',
      sample_id: 'e2e-vqa-sample',
      target: 'vqa',
      prompt: 'What is shown in this image?',
    },
    headers: {
      Authorization: `Bearer ${liveAuth.token}`,
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
