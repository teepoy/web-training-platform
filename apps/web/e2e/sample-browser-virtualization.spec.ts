import { test, expect, type Page } from '@playwright/test'

const orgId = 'org-e2e-1'
const datasetId = 'dataset-virt-1'

function make200Samples() {
  return Array.from({ length: 200 }, (_, i) => ({
    id: `sample-virt-${i + 1}`,
    dataset_id: datasetId,
    image_uris: [`memory://sample-${i + 1}.png`],
    metadata: { split: 'val' },
    latest_annotation: null,
  }))
}

async function mockVirtApi(page: Page) {
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
            name: 'virt-dataset',
            dataset_type: 'image_classification',
            task_spec: { task_type: 'classification', label_space: ['cat', 'dog'] },
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
          name: 'virt-dataset',
          dataset_type: 'image_classification',
          task_spec: { task_type: 'classification', label_space: ['cat', 'dog'] },
          created_at: '2026-01-01T00:00:00Z',
          org_id: orgId,
          org_name: 'E2E Org',
          is_public: false,
          ls_project_id: '200',
          ls_project_url: 'http://localhost:8080/projects/200',
        }),
      })
    }),
    page.route(`**/api/v1/datasets/${datasetId}/samples-with-labels**`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: make200Samples(), total: 200 }),
      })
    }),
    page.route(`**/api/v1/datasets/${datasetId}/annotation-stats`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total_samples: 200,
          annotated_samples: 0,
          unlabeled_samples: 200,
          label_counts: {},
        }),
      })
    }),
    page.route('**/api/v1/models', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }),
    page.route('**/api/v1/prediction-jobs', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }),
    page.route('**/api/v1/training-jobs', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }),
    page.route('**/api/v1/training-presets', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }),
    page.route('**/api/v1/export-formats', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([{ format_id: 'annotation-version-full-context-v1' }]),
      })
    }),
  ])
}

test.describe('shared browser virtualization', () => {
  test('renders only a bounded subset of nodes for large item sets', async ({ page }) => {
    await mockVirtApi(page)

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

    await page.goto(`/datasets/${datasetId}/classify`)
    await page.waitForSelector('[data-sb-item]')

    const renderedCount = await page.locator('[data-sb-item]').count()
    expect(renderedCount).toBeLessThan(50)
    expect(renderedCount).toBeGreaterThan(0)
  })
})
