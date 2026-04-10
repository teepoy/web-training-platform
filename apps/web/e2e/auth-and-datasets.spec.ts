import { expect, test, type Page } from '@playwright/test'

const orgId = 'org-e2e-1'
const authToken = 'e2e-token'

function mockCoreApi(page: Page) {
  return Promise.all([
    page.route('**/api/v1/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ access_token: authToken, token_type: 'bearer' }),
      })
    }),
    page.route('**/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'user-e2e-1',
          email: 'e2e@example.com',
          name: 'E2E User',
          is_superadmin: false,
          is_active: true,
          created_at: '2026-01-01T00:00:00Z',
          organizations: [
            {
              id: 'membership-e2e-1',
              user_id: 'user-e2e-1',
              org_id: orgId,
              role: 'admin',
              created_at: '2026-01-01T00:00:00Z',
            },
          ],
        }),
      })
    }),
    page.route('**/api/v1/organizations', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: orgId,
            name: 'E2E Org',
            slug: 'e2e-org',
            created_at: '2026-01-01T00:00:00Z',
          },
        ]),
      })
    }),
    page.route('**/api/v1/datasets', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'dataset-e2e-1',
            name: 'flowers-dataset',
            dataset_type: 'image_classification',
            task_spec: {
              task_type: 'classification',
              label_space: ['rose', 'tulip'],
            },
            created_at: '2026-01-01T00:00:00Z',
            org_id: orgId,
            org_name: 'E2E Org',
            is_public: false,
          },
        ]),
      })
    }),
  ])
}

test('redirects unauthenticated users to login', async ({ page }) => {
  await page.goto('/datasets')
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByPlaceholder('you@example.com')).toBeVisible()
})

test('logs in and shows datasets list', async ({ page }) => {
  await mockCoreApi(page)

  await page.goto('/login')
  await page.getByPlaceholder('you@example.com').fill('e2e@example.com')
  await page.getByPlaceholder('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign In' }).click()

  await expect(page).toHaveURL(/\/datasets$/)
  await expect(page.getByRole('heading', { name: 'Datasets' })).toBeVisible()
  await expect(page.getByText('flowers-dataset')).toBeVisible()
})
