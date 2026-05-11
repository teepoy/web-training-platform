import type { Page } from '@playwright/test'

/**
 * Login via the real Naive UI form.
 *
 * Navigates to /login, fills email + password inputs via placeholder selectors,
 * clicks "Sign In", and waits for redirect to /datasets.
 *
 * The login form uses Naive UI components:
 *   - Email input: placeholder="you@example.com"
 *   - Password input: placeholder="Password"
 *   - Submit button: "Sign In" text
 */
export async function loginViaUI(
  page: Page,
  email: string,
  password: string,
): Promise<void> {
  await page.goto('/login')

  // Fill the Naive UI form fields by their placeholder text
  await page.getByPlaceholder('you@example.com').fill(email)
  await page.getByPlaceholder('Password').fill(password)

  // Submit the form
  await page.getByRole('button', { name: 'Sign In' }).click()

  // After successful login, the router pushes to /datasets
  await page.waitForURL('**/datasets')
}

/**
 * Logout via the avatar dropdown in the layout header.
 *
 * Clicks the n-avatar in the top header bar to open the dropdown,
 * selects the "Logout" option, and waits for redirect to /login.
 *
 * NOTE: The "Logout" option only appears when auth is enabled
 * (authStore.authEnabled is true). In dev/live-stack mode with seed
 * credentials, this should always be visible.
 */
export async function logoutViaUI(page: Page): Promise<void> {
  // Click the avatar inside the header to open the Naive UI dropdown
  await page.locator('.n-layout-header .n-avatar').click()

  // The dropdown renders in a teleported overlay — select the Logout option
  await page.locator('.n-dropdown-option').filter({ hasText: 'Logout' }).click()

  // Wait for redirect to the login page
  await page.waitForURL('**/login')
}

/**
 * Register a new account via the real Naive UI form.
 *
 * Navigates to /register, fills name + email + password inputs,
 * clicks "Create Account", and waits for redirect to /datasets.
 *
 * The register form uses Naive UI components:
 *   - Name input: placeholder="Your name"
 *   - Email input: placeholder="you@example.com"
 *   - Password input: placeholder="Password"
 *   - Submit button: "Create Account" text
 */
export async function registerViaUI(
  page: Page,
  name: string,
  email: string,
  password: string,
): Promise<void> {
  await page.goto('/register')

  await page.getByPlaceholder('Your name').fill(name)
  await page.getByPlaceholder('you@example.com').fill(email)
  await page.getByPlaceholder('Password').fill(password)

  await page.getByRole('button', { name: 'Create Account' }).click()

  // After successful registration, the router pushes to /datasets
  await page.waitForURL('**/datasets')
}
