import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { goToDatasetDetail } from '../helpers/navigation';

/**
 * Live-stack Playwright sample tests.
 *
 * These tests run against a real backend (API_URL) and frontend (WEB_URL).
 * They assume the live stack is already seeded with at least the default
 * seed credentials (seed@example.com / seed1234).
 *
 * Each test creates its own dataset to avoid cross-test interference.
 */

const SEED_EMAIL = 'seed@example.com';
const SEED_PASSWORD = 'seed1234';

/** Small helper to create a dataset via the platform API from the browser. */
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

test('create sample with image upload', async ({ page }) => {
  const datasetName = `e2e-samples-upload-${Date.now()}`;

  // 1. Login
  await loginViaUI(page, SEED_EMAIL, SEED_PASSWORD);

  // 2. Create dataset via API (reliable / no UI plugin complexity)
  const dataset = await createDatasetViaApi(page, datasetName, ['cat', 'dog']);

  // 3. Navigate to dataset detail
  await page.goto('/datasets');
  await goToDatasetDetail(page, dataset.name);

  // 4. Wait for the Add Sample button to be visible
  await expect(page.getByRole('button', { name: 'Add Sample' })).toBeVisible();

  // 5. Click "Add Sample" to open the import flow modal
  await page.getByRole('button', { name: 'Add Sample' }).click();

  // 6. PluginFlowModal step 1: Select "Manual Sample Entry" plugin type
  await expect(page.getByText('Manual Sample Entry')).toBeVisible();
  await page.getByText('Manual Sample Entry').click();

  // 7. Step 2: ManualImporter form is now visible — upload an image
  const fileInput = page.locator('input[type="file"]').first();
  await expect(fileInput).toBeAttached();

  // Create an in-memory test image (tiny 1x1 PNG)
  const pngBytes = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPj/HwADBwIAMCbHYQAAAABJRU5ErkJggg==',
    'base64',
  );
  await fileInput.setInputFiles({
    name: 'test-sample.png',
    mimeType: 'image/png',
    buffer: pngBytes,
  });

  // Verify the preview image appears
  await expect(page.locator('.n-image img').first()).toBeVisible({ timeout: 5000 });

  // 8. Click "Create" to submit the sample
  await page.getByRole('button', { name: 'Create' }).click();

  // 9. Wait for success toast
  await expect(page.locator('.n-message', { hasText: 'Sample created' })).toBeVisible({
    timeout: 10000,
  });

  // 10. The modal should close (or the sample list should reload).
  //     Verify a sample item appears in the browser grid.
  await expect(page.locator('[data-sb-item]').first()).toBeVisible({ timeout: 10000 });
});

test('annotate sample with label', async ({ page }) => {
  const datasetName = `e2e-samples-annot-${Date.now()}`;

  // 1. Login
  await loginViaUI(page, SEED_EMAIL, SEED_PASSWORD);

  // 2. Create dataset with label space
  const dataset = await createDatasetViaApi(page, datasetName, ['rose', 'tulip']);

  // 3. Also create a sample via API so we have one to annotate
  await page.evaluate(
    async ({ dsId }) => {
      const token = localStorage.getItem('auth_token');
      const resp = await fetch(`/api/v1/datasets/${dsId}/samples`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          image_uris: ['memory://annot-test.png'],
          metadata: { source: 'e2e' },
        }),
      });
      if (!resp.ok) {
        throw new Error(`Create sample failed: ${resp.status}`);
      }
    },
    { dsId: dataset.id },
  );

  // 4. Navigate to dataset detail
  await page.goto('/datasets');
  await goToDatasetDetail(page, dataset.name);

  // 5. Wait for sample browser items to appear
  await expect(page.locator('[data-sb-item]').first()).toBeVisible({ timeout: 10000 });

  // 6. Click on the sample to open the Sample Detail drawer
  await page.locator('[data-sb-item]').first().click();
  await expect(page.getByText('Sample Detail')).toBeVisible({ timeout: 5000 });

  // 7. The drawer has an "Add Annotation" section with a label selector.
  //     Select the first label from the dropdown.
  const labelSelect = page.locator('.n-drawer .n-select').first();
  await labelSelect.click();

  // The n-select dropdown renders in a teleported overlay
  const selectOption = page.locator('.n-base-select-option').filter({ hasText: 'rose' });
  await expect(selectOption).toBeVisible({ timeout: 5000 });
  await selectOption.click();

  // 8. Click the "Add" button to submit the annotation
  await page.locator('.n-drawer').getByRole('button', { name: 'Add' }).first().click();

  // 9. Verify the annotation appears in the annotations list
  await expect(
    page.locator('.n-drawer .n-tag').filter({ hasText: 'rose' }).first(),
  ).toBeVisible({ timeout: 10000 });

  // 10. Also verify the annotation row is present (not in editing mode)
  await expect(
    page.locator('.n-drawer').getByRole('button', { name: 'Edit' }),
  ).toBeVisible({ timeout: 5000 });
});
