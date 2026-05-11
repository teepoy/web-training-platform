import { test, expect } from '@playwright/test'
import { loginViaUI, registerViaUI, logoutViaUI } from '../helpers/auth'

test.describe('Auth Flow', () => {
  test.describe('without existing session', () => {
    test.use({ storageState: { cookies: [], origins: [] } })

    test('registration creates new user', async ({ page }) => {
      const uniqueEmail = `e2e-reg-${Date.now()}@test.com`
      await registerViaUI(page, 'E2E Test', uniqueEmail, 'test1234')
      await expect(page).toHaveURL(/\/datasets/)
      await expect(page.locator('.n-layout-header .n-avatar')).toBeVisible()
    })

    test('login with seed credentials', async ({ page }) => {
      await loginViaUI(page, 'seed@example.com', 'seed1234')
      await expect(page).toHaveURL(/\/datasets/)
      await expect(page.locator('.n-layout-header .n-avatar')).toBeVisible()
    })

    test('login with invalid password shows error', async ({ page }) => {
      await page.goto('/login')
      await page.getByPlaceholder('you@example.com').fill('seed@example.com')
      await page.getByPlaceholder('Password').fill('wrongpassword')
      await page.getByRole('button', { name: 'Sign In' }).click()

      // Should stay on the login page (no redirect)
      await expect(page).not.toHaveURL(/\/datasets/)

      // Look for an error message — Naive UI message toast or form feedback
      const errorLocator = page.locator('.n-message, .n-form-item-feedback--error')
      await expect(errorLocator.first()).toBeVisible({ timeout: 10000 })
    })

    test('protected route redirects when unauthenticated', async ({ page }) => {
      await page.goto('/datasets')
      await page.waitForURL('**/login')
      await expect(page).toHaveURL(/\/login/)
    })
  })

  test('logout redirects to login', async ({ page }) => {
    // Already authenticated via the globalSetup storage state
    await expect(page.locator('.n-layout-header .n-avatar')).toBeVisible()
    await logoutViaUI(page)
    await expect(page).toHaveURL(/\/login/)
  })
})
