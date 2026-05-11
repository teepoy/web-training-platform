import { expect, test } from '@playwright/test'
import { goToSchedules, loginViaUI, waitForToast } from '../helpers'

const SCHEDULE_NAME = `e2e-live-sched-${Date.now()}`
const SCHEDULE_CRON = '0 6 * * 1'

test('list schedules page loads', async ({ page }) => {
  await loginViaUI(page, 'seed@example.com', 'seed1234')
  await goToSchedules(page)

  await expect(
    page.locator('.n-page-header').filter({ hasText: 'Schedules' }),
  ).toBeVisible()

  await expect(page.locator('.n-data-table')).toBeVisible()

  await expect(
    page.getByRole('button', { name: 'Create Schedule' }),
  ).toBeVisible()
})

test('create schedule', async ({ page }) => {
  await loginViaUI(page, 'seed@example.com', 'seed1234')
  await goToSchedules(page)

  await page.getByRole('button', { name: 'Create Schedule' }).click()

  const dialog = page.locator('.n-dialog')
  await expect(dialog).toBeVisible()

  await dialog.getByPlaceholder('my-schedule').fill(SCHEDULE_NAME)

  await dialog.getByPlaceholder('Select a flow').click()
  await page.locator('.n-base-select-option').filter({ hasText: 'drain-dataset' }).click()

  await dialog.getByPlaceholder('*/5 * * * *').fill(SCHEDULE_CRON)

  await dialog.getByRole('button', { name: 'Create' }).click()

  await waitForToast(page, 'Schedule created')

  await expect(page.locator('.n-data-table').filter({ hasText: SCHEDULE_NAME })).toBeVisible()

  const row = page.locator('.n-data-table tr', {
    has: page.getByText(SCHEDULE_NAME),
  })
  await expect(row).toBeVisible()

  await expect(
    row.locator('.n-tag').filter({ hasText: 'active' }),
  ).toBeVisible()
})

test('pause and resume schedule', async ({ page }) => {
  await loginViaUI(page, 'seed@example.com', 'seed1234')
  await goToSchedules(page)

  await expect(page.locator('.n-data-table')).toBeVisible()

  const row = page.locator('.n-data-table tr', {
    has: page.getByText(SCHEDULE_NAME),
  })
  await expect(row).toBeVisible()

  const pauseButton = row.getByRole('button', { name: 'Pause' })
  await expect(pauseButton).toBeVisible()
  await pauseButton.click()

  await waitForToast(page, 'Schedule paused')

  await expect(
    row.locator('.n-tag').filter({ hasText: 'paused' }),
  ).toBeVisible({ timeout: 5000 })

  const resumeButton = row.getByRole('button', { name: 'Resume' })
  await expect(resumeButton).toBeVisible()
  await resumeButton.click()

  await waitForToast(page, 'Schedule resumed')

  await expect(
    row.locator('.n-tag').filter({ hasText: 'active' }),
  ).toBeVisible({ timeout: 5000 })
})
