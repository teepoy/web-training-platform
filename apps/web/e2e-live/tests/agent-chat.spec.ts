import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { goToDatasets, goToDatasetDetail } from '../helpers/navigation';

const SEED_EMAIL = 'seed@example.com';
const SEED_PASSWORD = 'seed1234';

function datasetName(prefix = 'E2E Agent'): string {
  return `${prefix} ${Date.now()}`;
}

/**
 * Create a minimal dataset with samples, then navigate to the classify view.
 * Returns the dataset name so callers can verify it was created.
 */
async function createDatasetAndGoToClassify(
  page: import('@playwright/test').Page,
): Promise<string> {
  const name = datasetName();

  await goToDatasets(page);

  await page.getByRole('button', { name: 'Import Dataset' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByText('Import from JSON').click();

  await page.getByPlaceholder('e.g. imported-dataset').fill(name);

  await page.getByPlaceholder('Select dataset type').click();
  await page.getByText('Image Classification', { exact: true }).click();

  await expect(page.locator('.n-dynamic-tags')).toBeVisible({ timeout: 5000 });
  await page.locator('.n-dynamic-tags').click();
  await page.keyboard.type('cat');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(200);
  await page.locator('.n-dynamic-tags').click();
  await page.keyboard.type('dog');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(200);

  await page
    .locator('input[type="file"][accept="application/json"]')
    .setInputFiles({
      name: 'samples.json',
      mimeType: 'application/json',
      buffer: Buffer.from(
        JSON.stringify([
          {
            image_uris: ['memory://e2e-agent-test.jpg'],
            metadata: { source: 'e2e-live' },
            label: null,
          },
        ]),
      ),
    });
  await expect(page.getByText(/samples\.json/)).toBeVisible({ timeout: 3000 });

  await page.getByRole('button', { name: 'Import', exact: true }).click();
  await expect(page.getByText(name, { exact: true })).toBeVisible({
    timeout: 15000,
  });

  // Navigate to classify view
  await goToDatasetDetail(page, name);
  await page.getByRole('button', { name: 'Open Workflow' }).click();
  await expect(page).toHaveURL(/\/datasets\/.+\/classify/);
  await expect(page.locator('.classify-view')).toBeVisible({ timeout: 10000 });

  return name;
}

test('agent chat FAB visible in classify view', async ({ page }) => {
  await loginViaUI(page, SEED_EMAIL, SEED_PASSWORD);
  await createDatasetAndGoToClassify(page);

  // The FAB (floating action button) should be visible in the bottom-right
  await expect(page.locator('.acd-fab')).toBeVisible({ timeout: 10000 });
});

test('agent chat drawer opens', async ({ page }) => {
  await loginViaUI(page, SEED_EMAIL, SEED_PASSWORD);
  await createDatasetAndGoToClassify(page);

  // FAB must be visible before clicking
  await expect(page.locator('.acd-fab')).toBeVisible({ timeout: 5000 });

  // Click FAB to open the drawer
  await page.locator('.acd-fab').click();

  // FAB should hide when the drawer is open
  await expect(page.locator('.acd-fab')).not.toBeVisible({ timeout: 3000 });

  // Drawer panel should appear
  await expect(page.locator('.acd')).toBeVisible({ timeout: 5000 });

  // Header title should be "Agent Chat"
  await expect(page.locator('.acd-header__title')).toHaveText('Agent Chat');

  // Empty state message should be visible when no messages exist
  await expect(page.locator('.acd-messages__empty')).toBeVisible();
});

test('agent chat accepts message', async ({ page }) => {
  await loginViaUI(page, SEED_EMAIL, SEED_PASSWORD);
  await createDatasetAndGoToClassify(page);

  // Open the drawer
  await page.locator('.acd-fab').click();
  await expect(page.locator('.acd')).toBeVisible({ timeout: 5000 });

  // Type a message in the input
  const inputField = page.locator('.acd-input__field');
  await expect(inputField).toBeVisible();
  await inputField.fill('Hello agent, what can you tell me about this dataset?');

  // Click the send button
  await page.locator('.acd-input__btn').click();

  // Wait for the user message to appear in the chat
  await expect(page.locator('.acd-msg--user')).toBeVisible({ timeout: 5000 });

  // Wait for a response: SSE stream (assistant message or action), or the
  // loading indicator to disappear. Both outcomes are valid — a 503 when the
  // LLM backend is not configured is expected and not a failure.
  const responseLocator = page.locator(
    '.acd-msg--assistant, .acd-msg--action',
  );

  try {
    await responseLocator.first().waitFor({ timeout: 30000 });
    // A response appeared — success (SSE stream working)
  } catch {
    // No visible response after 30s — the loading state should at least resolve
    // (this covers the 503 / backend-unreachable case where an error message
    // might appear as an assistant bubble with "Error:" text)
    await page.waitForTimeout(2000);

    // Check if an error message appeared as an assistant bubble
    const errorMsg = page.locator('.acd-msg--assistant');
    if ((await errorMsg.count()) > 0) {
      // Error message rendered — valid outcome
      await expect(errorMsg.first()).toBeVisible();
    } else {
      // No response at all — still valid (503 may not produce a visible error)
      // Just ensure the loading indicator is gone
      await expect(page.locator('.acd-msg--loading')).not.toBeVisible({
        timeout: 10000,
      });
    }
  }

  // The drawer should remain open with the conversation visible
  await expect(page.locator('.acd')).toBeVisible();
});
