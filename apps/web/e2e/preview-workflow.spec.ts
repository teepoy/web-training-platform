import { expect, test, type Page } from '@playwright/test'

const orgId = 'org-e2e-1'
const authToken = 'e2e-token'
const datasetId = 'dataset-preview-1'
const sessionId = 'sess-123'
const collectionRef = 'test-collection'

async function mockPreviewWorkflowApi(page: Page) {
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
        body: JSON.stringify([]),
      })
    }),
    
    page.route(`**/api/v1/preview-sessions/expired-session`, async (route) => {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'preview session expired or not found' }),
      })
    }),
    
    page.route(`**/api/v1/preview-sessions/${sessionId}/items?limit=**`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            { upstream_item_id: 'item-1', image_uris: ['memory://item-1.png'], metadata: {} },
            { upstream_item_id: 'item-2', image_uris: ['memory://item-2.png'], metadata: {} }
          ],
          next_cursor: 'cursor-2',
          has_more: true,
          estimated_total: 50
        }),
      })
    }),

    page.route(`**/api/v1/preview-sessions/${sessionId}/items?limit=**&cursor=cursor-2`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            { upstream_item_id: 'item-3', image_uris: ['memory://item-3.png'], metadata: {} }
          ],
          next_cursor: 'cursor-3',
          has_more: false,
          estimated_total: 50
        }),
      })
    }),
    
    page.route(`**/api/v1/preview-sessions/${sessionId}/persist`, async (route) => {
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({
          dataset_id: datasetId,
          persist_session_id: 'persist-123',
          status: 'running',
          imported_count: 0,
          remaining_count: 3
        }),
      })
    }),

    page.route(`**/api/v1/preview-sessions/${sessionId}/persist-status`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          dataset_id: datasetId,
          persist_session_id: 'persist-123',
          status: 'completed',
          imported_count: 3,
          remaining_count: 0
        }),
      })
    }),

    page.route(`**/api/v1/preview-sessions/${sessionId}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          session_id: sessionId,
          collection_ref: collectionRef,
          classification_enabled: true,
          estimated_total: 50,
          loaded_count: 20,
          next_cursor: 'cursor-20',
          has_more: true
        }),
      })
    }),

    page.route('**/api/v1/preview-sessions', async (route) => {
      if (route.request().method() === 'POST') {
        const body = route.request().postDataJSON()
        expect(body).toMatchObject({ collection_ref: collectionRef })
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            session_id: sessionId,
            collection_ref: collectionRef,
            classification_enabled: true,
            estimated_total: 50,
            loaded_count: 20,
            next_cursor: 'cursor-20',
            has_more: true
          }),
        })
      } else {
        await route.continue()
      }
    }),
  ])
}

test('runs preview launch and workspace flow', async ({ page }) => {
  await mockPreviewWorkflowApi(page)

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

  await page.goto('/preview')
  await expect(page.getByText('Preview Dataset')).toBeVisible()
  await page.getByPlaceholder('e.g. imagenet-1k-sample').fill(collectionRef)
  await page.getByRole('button', { name: 'Preview' }).click()
  
  await page.waitForURL(`**/preview/${sessionId}`)

  await expect(page.getByRole('button', { name: 'Persist Dataset' })).toBeVisible()
  await expect.poll(async () => page.locator('[data-sb-item]').count()).toBeGreaterThan(0)

  await expect(page.getByRole('radio', { name: 'Grid' })).toBeVisible()
  await expect(page.getByRole('radio', { name: 'List' })).toBeVisible()

  await expect(page.locator('.cs-header__toggle')).toBeVisible()

  await expect(page.getByRole('button', { name: /Submit/ })).toHaveCount(0)

  await page.waitForSelector('[data-sb-item]')
  const itemCount = await page.locator('[data-sb-item]').count()
  expect(itemCount).toBeGreaterThan(0)

  await page.locator('.n-radio__label', { hasText: 'List' }).click()
  const firstListImage = page.locator('[data-sb-item] img, .sb-list-img').first()
  await expect(firstListImage).toBeVisible()
  await expect
    .poll(async () => firstListImage.evaluate((el) => el.getBoundingClientRect().width))
    .toBeGreaterThanOrEqual(100)

  await page.getByRole('button', { name: 'Persist Dataset' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  
  await expect(page.getByLabel('Entire collection (recommended)')).toBeChecked()
  
  await page.getByRole('button', { name: 'Persist', exact: true }).click()
  
  await page.waitForURL(`**/datasets/${datasetId}/classify?previewPersistSession=${sessionId}`)
})

test('shows error for expired session', async ({ page }) => {
  await mockPreviewWorkflowApi(page)
  
  await page.addInitScript(() => {
    window.localStorage.clear()
    window.sessionStorage.clear()
    window.localStorage.setItem('auth_token', 'e2e-token')
  })

  await page.goto('/preview/expired-session')
  await expect(page.getByText('Preview session not found or expired.')).toBeVisible()
})
