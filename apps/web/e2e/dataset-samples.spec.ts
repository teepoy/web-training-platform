import { expect, test, type Page } from '@playwright/test'

const orgId = 'org-e2e-1'
const datasetId = 'dataset-ds-1'

async function mockDatasetSamplesApi(page: Page) {
  await Promise.all([
    page.route('**/api/v1/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ access_token: 'e2e-token', token_type: 'bearer' }),
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
          { id: orgId, name: 'E2E Org', slug: 'e2e-org', created_at: '2026-01-01T00:00:00Z' },
        ]),
      })
    }),
    page.route('**/api/v1/datasets', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: datasetId,
            name: 'flowers-dataset',
            dataset_type: 'image_classification',
            task_spec: { task_type: 'classification', label_space: ['rose', 'tulip'] },
            created_at: '2026-01-01T00:00:00Z',
            org_id: orgId,
            org_name: 'E2E Org',
            is_public: false,
          },
        ]),
      })
    }),
    page.route(`**/api/v1/datasets/${datasetId}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: datasetId,
          name: 'flowers-dataset',
          dataset_type: 'image_classification',
          task_spec: { task_type: 'classification', label_space: ['rose', 'tulip'] },
          created_at: '2026-01-01T00:00:00Z',
          org_id: orgId,
          org_name: 'E2E Org',
          is_public: false,
          ls_project_id: '101',
          ls_project_url: 'http://localhost:8080/projects/101',
        }),
      })
    }),
    page.route(`**/api/v1/datasets/${datasetId}/samples-with-labels**`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 'sample-ds-1',
              dataset_id: datasetId,
              image_uris: ['memory://sample-ds-1.png'],
              metadata: { split: 'train' },
              latest_annotation: null,
            },
            {
              id: 'sample-ds-2',
              dataset_id: datasetId,
              image_uris: ['memory://sample-ds-2.png'],
              metadata: { split: 'val' },
              latest_annotation: null,
            },
          ],
          total: 2,
        }),
      })
    }),
    page.route(`**/api/v1/datasets/${datasetId}/annotation-stats`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total_samples: 2,
          annotated_samples: 0,
          unlabeled_samples: 2,
          label_counts: {},
        }),
      })
    }),
    page.route(`**/api/v1/datasets/${datasetId}/samples/sample-ds-1`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'sample-ds-1',
          dataset_id: datasetId,
          image_uris: ['memory://sample-ds-1.png'],
          metadata: { split: 'train' },
          created_at: '2026-01-01T00:00:00Z',
        }),
      })
    }),
    page.route(`**/api/v1/datasets/${datasetId}/samples/sample-ds-1/annotations`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
    }),
    page.route(`**/api/v1/datasets/${datasetId}/samples/sample-ds-1/predictions`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
    }),
    page.route(`**/api/v1/datasets/${datasetId}/samples/sample-ds-1/similar`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
    }),
    page.route('**/api/v1/export-formats', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{ format_id: 'annotation-version-full-context-v1' }]),
      })
    }),
    page.route('**/api/v1/training-jobs', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }),
    page.route('**/api/v1/training-presets', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }),
  ])
}

test('dataset Samples tab shows shared browser controls and opens Sample Detail', async ({ page }) => {
  await mockDatasetSamplesApi(page)

  await page.addInitScript(() => {
    window.localStorage.clear()
    window.sessionStorage.clear()
    window.localStorage.setItem('auth_token', 'e2e-token')
    window.localStorage.setItem('auth_user', JSON.stringify({
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
          org_id: 'org-e2e-1',
          role: 'admin',
          created_at: '2026-01-01T00:00:00Z',
        },
      ],
    }))
  })

  await page.goto(`/datasets/${datasetId}`)

  await expect(page.getByRole('radio', { name: 'Grid' })).toBeVisible()
  await expect(page.getByRole('radio', { name: 'List' })).toBeVisible()

  await expect(page.locator('.cs-header__toggle')).toBeVisible()

  await page.waitForSelector('[data-sb-item]')
  const itemCount = await page.locator('[data-sb-item]').count()
  expect(itemCount).toBeGreaterThan(0)

  await page.locator('[data-sb-item]').first().click()
  await expect(page.getByText('Sample Detail')).toBeVisible()
})
