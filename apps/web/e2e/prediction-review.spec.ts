import { expect, test, type Page } from '@playwright/test'

const orgId = 'org-e2e-1'
const authToken = 'e2e-token'
const datasetId = 'dataset-review-1'
const modelId = 'model-review-1'
const predictionJobId = 'prediction-job-1'

async function mockPredictionReviewApi(page: Page) {
  let predictionJobPolls = 0

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
        body: JSON.stringify([
          {
            id: datasetId,
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
    page.route('**/api/v1/models', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: modelId,
            uri: 'memory://models/model-review-1',
            kind: 'model',
            name: 'flower-classifier',
            file_size: 123,
            file_hash: 'abc123',
            format: 'pytorch',
            created_at: '2026-01-01T00:00:00Z',
            metadata: {
              dataset_types: ['image_classification'],
              task_types: ['classification'],
              prediction_targets: ['image_classification'],
              label_space: ['rose', 'tulip'],
            },
            job_id: 'job-review-1',
            dataset_id: datasetId,
            dataset_name: 'flowers-dataset',
            preset_name: 'resnet50-cls-v1',
          },
        ]),
      })
    }),
    page.route('**/api/v1/prediction-jobs', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        })
        return
      }
      await route.continue()
    }),
    page.route('**/api/v1/export-formats', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { format_id: 'annotation-version-full-context-v1' },
          { format_id: 'annotation-version-compact-v1' },
        ]),
      })
    }),
    page.route('**/api/v1/predictions/run', async (route) => {
      const body = route.request().postDataJSON()
      expect(body).toMatchObject({
        dataset_id: datasetId,
        model_id: modelId,
        target: 'image_classification',
      })
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({
          id: predictionJobId,
          dataset_id: datasetId,
          model_id: modelId,
          status: 'queued',
          created_by: 'user-e2e-1',
          target: 'image_classification',
          model_version: null,
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          external_job_id: null,
          sample_ids: null,
          summary: {
            processed: 0,
            total_samples: 2,
          },
        }),
      })
    }),
    page.route(`**/api/v1/prediction-jobs/${predictionJobId}`, async (route) => {
      predictionJobPolls += 1
      const completed = predictionJobPolls >= 2
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: predictionJobId,
          dataset_id: datasetId,
          model_id: modelId,
          status: completed ? 'completed' : 'running',
          created_by: 'user-e2e-1',
          target: 'image_classification',
          model_version: null,
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          external_job_id: null,
          sample_ids: null,
          summary: completed
            ? {
                processed: 2,
                total_samples: 2,
                predictions: [
                  {
                    sample_id: 'sample-review-1',
                    ls_task_id: 11,
                    predicted_label: 'rose',
                    confidence: 0.91,
                    ls_prediction_id: 101,
                    error: null,
                  },
                  {
                    sample_id: 'sample-review-2',
                    ls_task_id: 12,
                    predicted_label: 'tulip',
                    confidence: 0.87,
                    ls_prediction_id: 102,
                    error: null,
                  },
                ],
              }
            : {
                processed: 1,
                total_samples: 2,
              },
        }),
      })
    }),
  ])
}

test('runs predictions from prediction review and loads results', async ({ page }) => {
  await mockPredictionReviewApi(page)

  await page.goto('/login')
  await page.getByPlaceholder('you@example.com').fill('e2e@example.com')
  await page.getByPlaceholder('Password').fill('password123')
  await page.getByRole('button', { name: 'Sign In' }).click()
  await expect(page).toHaveURL(/\/datasets$/)

  await page.goto('/prediction-review')
  await expect(page.locator('.n-page-header__title', { hasText: 'Prediction Review' })).toBeVisible()

  const setupCard = page.locator('.n-card').filter({ hasText: '1. Setup' })

  await setupCard.locator('.n-base-selection').filter({ hasText: 'Select dataset' }).click()
  await page.locator('.n-base-select-option').filter({ hasText: 'flowers-dataset' }).click()

  await setupCard.locator('.n-base-selection').filter({ hasText: 'Select model' }).click()
  await page.locator('.n-base-select-option').filter({ hasText: /flower-classifier/ }).click()

  await page.getByRole('button', { name: 'Run Predictions' }).click()

  const reviewCard = page.locator('.n-card').filter({ hasText: '2. Review Predictions' })

  await expect(page.getByText(/Prediction job submitted:/)).toBeVisible()
  await expect(page.getByText('2 predictions ready for review')).toBeVisible()
  await expect(reviewCard).toContainText('rose')
  await expect(reviewCard).toContainText('tulip')
  await expect(page.getByRole('button', { name: /Save as Annotation Version/ })).toBeVisible()
})
