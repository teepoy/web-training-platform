import { expect, test, type Page } from '@playwright/test'

const orgId = 'org-e2e-wafer'
const authToken = 'e2e-token'
const datasetId = 'dataset-wafer-1'

async function mockWaferMapApi(page: Page) {
  await Promise.all([
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
            name: 'wafer-dataset',
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
          name: 'wafer-dataset',
          dataset_type: 'image_classification',
          task_spec: { task_type: 'classification', label_space: ['rose', 'tulip'] },
          created_at: '2026-01-01T00:00:00Z',
          org_id: orgId,
          org_name: 'E2E Org',
          is_public: false,
          ls_project_id: '100',
          ls_project_url: 'http://localhost:8080/projects/100',
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
              id: 'sample-w1',
              dataset_id: datasetId,
              image_uris: ['memory://sample-w1.png'],
              metadata: { split: 'val', wafer_x: 0.1, wafer_y: 0.2 },
              latest_annotation: null,
            },
            {
              id: 'sample-w2',
              dataset_id: datasetId,
              image_uris: ['memory://sample-w2.png'],
              metadata: { split: 'val', wafer_x: -0.3, wafer_y: 0.5 },
              latest_annotation: null,
            },
            {
              id: 'sample-w3',
              dataset_id: datasetId,
              image_uris: ['memory://sample-w3.png'],
              metadata: { split: 'val', wafer_x: 0.7, wafer_y: -0.4 },
              latest_annotation: null,
            },
          ],
          total: 3,
        }),
      })
    }),
    page.route(`**/api/v1/datasets/${datasetId}/annotation-stats`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total_samples: 3,
          annotated_samples: 0,
          unlabeled_samples: 3,
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
    page.route(`**/api/v1/datasets/${datasetId}/query`, async (route) => {
      const body = route.request().postDataJSON()
      if (body?.query_type === 'wafer-points') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            query_type: 'wafer-points',
            points: [
              { id: 'sample-w1', x: 10_000_000, y: 20_000_000 },
              { id: 'sample-w2', x: -30_000_000, y: 50_000_000 },
              { id: 'sample-w3', x: 70_000_000, y: -40_000_000 },
            ],
          }),
        })
      } else {
        await route.continue()
      }
    }),
  ])
}

test('wafer-map panel renders with dieGrid config', async ({ page }) => {
  await mockWaferMapApi(page)

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
          org_id: 'org-e2e-wafer',
          role: 'admin',
          created_at: '2026-01-01T00:00:00Z',
        },
      ],
    }))
  })

  const pageErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))

  await page.goto(`/datasets/${datasetId}/classify`)

  await expect(page.locator('[data-testid="wafer-map-panel"]')).toBeVisible()
  await expect(page.locator('[data-testid="wafer-map-panel"] canvas')).toBeVisible()
  await expect(page.locator('[data-testid="wafer-map-panel"]')).not.toContainText('No wafer points')

  await expect(page.locator('[data-testid="wafer-map-panel"] .wmw-chart-wrap')).toBeVisible()

  expect(pageErrors).toHaveLength(0)

  await expect(page.locator('[data-testid="wafer-map-panel"] .wmw-footer')).toContainText('3 points')
})

test('wafer-map zoom + Reset Zoom button', async ({ page }) => {
  await mockWaferMapApi(page)

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
          org_id: 'org-e2e-wafer',
          role: 'admin',
          created_at: '2026-01-01T00:00:00Z',
        },
      ],
    }))
  })

  const pageErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))

  await page.goto(`/datasets/${datasetId}/classify`)

  await expect(page.locator('[data-testid="wafer-map-panel"]')).toBeVisible()
  await expect(page.locator('[data-testid="wafer-map-panel"] canvas')).toBeVisible()

  const resetZoomButton = page.locator('[data-testid="wafer-map-panel"]').getByRole('button', { name: 'Reset Zoom' })

  await expect(resetZoomButton).not.toBeVisible()

  const chartWrap = page.locator('[data-testid="wafer-map-panel"] .wmw-chart-wrap')
  const box = await chartWrap.boundingBox()
  expect(box).not.toBeNull()

  await page.evaluate(() => {
    const wrapper = document.querySelector('[data-testid="wafer-map-panel"] .wmw-chart-wrap')
    if (!wrapper) return
    const rect = wrapper.getBoundingClientRect()
    wrapper.dispatchEvent(new WheelEvent('wheel', {
      deltaY: -100,
      deltaX: 0,
      clientX: rect.left + rect.width / 2,
      clientY: rect.top + rect.height / 2,
      bubbles: true,
      cancelable: true,
    }))
  })

  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(resolve)))
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(resolve)))

  await expect(resetZoomButton).toBeVisible({ timeout: 10000 })

  await resetZoomButton.click()

  await expect(resetZoomButton).not.toBeVisible()

  expect(pageErrors).toHaveLength(0)
})
