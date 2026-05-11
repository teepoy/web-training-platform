import { test, expect } from '@playwright/test';
import { loginViaUI } from '../helpers/auth';
import { goToDashboard } from '../helpers/navigation';

const SEED_EMAIL = 'seed@example.com';
const SEED_PASSWORD = 'seed1234';

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaUI(page, SEED_EMAIL, SEED_PASSWORD);
    await goToDashboard(page);
  });

  test('dashboard loads statistics', async ({ page }) => {
    // Work Pool card with n-statistic components
    const workPoolCard = page.locator('.n-card').filter({ hasText: 'Work Pool' });
    await expect(workPoolCard).toBeVisible({ timeout: 10000 });

    // Job Queue card with n-statistic components
    const jobQueueCard = page.locator('.n-card').filter({ hasText: 'Job Queue' });
    await expect(jobQueueCard).toBeVisible({ timeout: 10000 });

    // Verify statistic labels within the cards
    await expect(workPoolCard.locator('.n-statistic').filter({ hasText: 'Pool Name' })).toBeVisible();
    await expect(workPoolCard.locator('.n-statistic').filter({ hasText: 'Type' })).toBeVisible();

    await expect(jobQueueCard.locator('.n-statistic').filter({ hasText: 'Queued' })).toBeVisible();
    await expect(jobQueueCard.locator('.n-statistic').filter({ hasText: 'Running' })).toBeVisible();
    await expect(jobQueueCard.locator('.n-statistic').filter({ hasText: 'Completed' })).toBeVisible();
    await expect(jobQueueCard.locator('.n-statistic').filter({ hasText: 'Failed' })).toBeVisible();
  });

  test('dashboard shows service health table', async ({ page }) => {
    const serviceHealthCard = page.locator('.n-card').filter({ hasText: 'Service Health' });
    await expect(serviceHealthCard).toBeVisible({ timeout: 10000 });

    // The service health table should contain a n-data-table
    const table = serviceHealthCard.locator('.n-data-table');
    await expect(table).toBeVisible();

    // Verify the table has service name entries (at minimum, check column headers)
    await expect(table.locator('th').filter({ hasText: 'Service' })).toBeVisible();
    await expect(table.locator('th').filter({ hasText: 'Status' })).toBeVisible();
  });

  test('dashboard shows recent items', async ({ page }) => {
    const recentJobsCard = page.locator('.n-card').filter({ hasText: 'Recent Jobs' });
    await expect(recentJobsCard).toBeVisible({ timeout: 10000 });

    // The recent jobs table should render
    const table = recentJobsCard.locator('.n-data-table');
    await expect(table).toBeVisible();

    // Verify the table column headers
    await expect(table.locator('th').filter({ hasText: 'ID' })).toBeVisible();
    await expect(table.locator('th').filter({ hasText: 'Status' })).toBeVisible();
  });
});
