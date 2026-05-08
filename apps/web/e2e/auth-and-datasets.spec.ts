import { expect, test, type Page } from '@playwright/test'

const orgId = 'org-e2e-1'
const authToken = 'e2e-token'

const baseUser = {
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
}

const flowerDataset = {
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
}

function mockCoreApi(page: Page, userOverrides: Partial<typeof baseUser> = {}) {
  const user = { ...baseUser, ...userOverrides }
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
        body: JSON.stringify(user),
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
        body: JSON.stringify([flowerDataset]),
      })
    }),
    page.route('**/api/v1/datasets/**', async (route) => {
      if (route.request().method() === 'DELETE') {
        await route.fulfill({ status: 204 })
      } else if (route.request().method() === 'PATCH') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(flowerDataset),
        })
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(flowerDataset),
        })
      }
    }),
  ])
}

function injectAuthToken(page: Page, user = baseUser) {
  return page.addInitScript((u) => {
    window.localStorage.setItem('auth_token', 'e2e-token')
    window.localStorage.setItem('auth_user', JSON.stringify(u))
  }, user)
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

test('import dataset button opens the plugin flow modal', async ({ page }) => {
  await mockCoreApi(page)
  await injectAuthToken(page)

  await page.goto('/datasets')
  await expect(page.getByText('flowers-dataset')).toBeVisible()

  await page.getByRole('button', { name: 'Import Dataset' }).click()

  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByText('Manual Sample Entry')).toBeVisible()
})

test('preview dataset button opens the plugin flow modal', async ({ page }) => {
  await mockCoreApi(page)
  await injectAuthToken(page)

  await page.goto('/datasets')
  await expect(page.getByText('flowers-dataset')).toBeVisible()

  await page.getByRole('button', { name: 'Preview Dataset' }).click()

  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByText('Upstream Collection')).toBeVisible()
})

test('row view button navigates to dataset detail', async ({ page }) => {
  await mockCoreApi(page)
  await injectAuthToken(page)

  await page.goto('/datasets')
  await expect(page.getByText('flowers-dataset')).toBeVisible()

  await page.getByRole('button', { name: 'View', exact: true }).click()

  await expect(page).toHaveURL(/\/datasets\/dataset-e2e-1/)
})

test('superadmin sees make-public and delete buttons for own-org datasets', async ({ page }) => {
  await mockCoreApi(page, { is_superadmin: true })
  await injectAuthToken(page, { ...baseUser, is_superadmin: true })

  await page.goto('/datasets')
  await expect(page.getByText('flowers-dataset')).toBeVisible()

  await expect(page.getByRole('button', { name: 'Make Public' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Delete' })).toBeVisible()
})

test('delete button triggers confirmation before calling the API', async ({ page }) => {
  await mockCoreApi(page, { is_superadmin: true })
  await injectAuthToken(page, { ...baseUser, is_superadmin: true })

  let deleteApiCalled = false
  await page.route('**/api/v1/datasets/dataset-e2e-1', async (route) => {
    if (route.request().method() === 'DELETE') {
      deleteApiCalled = true
      await route.fulfill({ status: 204 })
    } else {
      await route.continue()
    }
  })

  page.on('dialog', (dialog) => dialog.accept())

  await page.goto('/datasets')
  await expect(page.getByText('flowers-dataset')).toBeVisible()

  await page.getByRole('button', { name: 'Delete' }).click()

  await expect.poll(() => deleteApiCalled, { timeout: 3000 }).toBe(true)
})
