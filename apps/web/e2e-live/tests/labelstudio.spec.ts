import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { goToDatasetDetail } from '../helpers/navigation';

const SEED_EMAIL = 'seed@example.com';
const SEED_PASSWORD = 'seed1234';

/**
 * Create a dataset via the platform API from the browser context.
 * Returns the dataset { id, name } for subsequent navigation.
 */
async function createDatasetViaApi(
  page: import('@playwright/test').Page,
  name: string,
  labelSpace: string[],
): Promise<{ id: string; name: string }> {
  return page.evaluate(
    async ({ n, ls }) => {
      const token = localStorage.getItem('auth_token');
      const resp = await fetch('/api/v1/datasets', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: n,
          dataset_type: 'image_classification',
          task_spec: {
            task_type: 'classification',
            label_space: ls,
          },
        }),
      });
      if (!resp.ok) {
        throw new Error(`Create dataset failed: ${resp.status}`);
      }
      return resp.json() as Promise<{ id: string; name: string }>;
    },
    { n: name, ls: labelSpace },
  );
}

test('LS project link accessible from dataset detail', async ({ page }) => {
  const datasetName = `e2e-ls-${Date.now()}`;

  // 1. Login with seed credentials
  await loginViaUI(page, SEED_EMAIL, SEED_PASSWORD);

  // 2. Create a dataset via API — dataset creation auto-creates an LS project
  await createDatasetViaApi(page, datasetName, ['cat', 'dog']);

  // 3. Navigate to the dataset detail page
  await page.goto('/datasets');
  await goToDatasetDetail(page, datasetName);

  // 4. Verify the LS project link tag is visible in the header
  const lsTag = page.locator('.n-tag').filter({ hasText: /Label Studio Project #/ });
  await expect(lsTag).toBeVisible({ timeout: 10000 });

  // 5. The LS project link should point to localhost:8080 (the compose LS instance)
  const lsLink = lsTag.locator('a');
  const href = await lsLink.getAttribute('href');
  expect(href).toBeTruthy();
  expect(href!).toContain('localhost:8080');
});
