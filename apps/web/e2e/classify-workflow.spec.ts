import { expect, test, type Page } from '@playwright/test'

const orgId = 'org-e2e-1'
const authToken = 'e2e-token'
const datasetId = 'dataset-review-1'
const modelId = 'model-review-1'
const predictionJobId = 'prediction-job-1'

async function mockClassifyWorkflowApi(page: Page) {
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
    page.route(`**/api/v1/datasets/${datasetId}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
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
              id: 'sample-review-1',
              dataset_id: datasetId,
              image_uris: ['memory://sample-1.png'],
              metadata: { split: 'val' },
              latest_annotation: null,
            },
            {
              id: 'sample-review-2',
              dataset_id: datasetId,
              image_uris: ['memory://sample-2.png'],
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
    page.route('**/api/v1/training-jobs', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      })
    }),
    page.route('**/api/v1/training-presets', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'preset-e2e-1',
            name: 'resnet50-cls-v1',
            trainable: true,
            compatibility: {
              dataset_types: ['image_classification'],
              task_types: ['classification'],
            },
          },
        ]),
      })
    }),
    page.route('**/api/v1/task-tracker/tasks/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: predictionJobId,
          task_kind: 'prediction',
          meta: {},
          raw: {
            platform_job: {},
            flow_run: null,
            deployment: null,
            work_queue: null,
            work_pool: null,
            logs: [],
          },
          derived: {
            task_kind: 'prediction',
            execution_kind: 'prefect',
            display_status: 'running',
            prefect_state: null,
            stage: 'running',
            active_node: null,
            capacity_status: 'unknown',
            queue_priority: null,
            queue_priority_label: 'none',
            queue_depth_ahead: null,
            pool_concurrency_limit: null,
            pool_slots_used: null,
            stages: [],
            scorecard: { errors: 0, warnings: 0, checks: [] },
            summary_metrics: {},
            artifacts: [],
            dynamic_console_lines: [],
            deep_links: {},
          },
        }),
      })
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
    page.route(`**/api/v1/datasets/${datasetId}/query`, async (route) => {
      const body = route.request().postDataJSON()
      if (body?.query_type === 'wafer-points') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            query_type: 'wafer-points',
            points: [
              { id: 'sample-review-1', x: 0.1, y: 0.2 },
              { id: 'sample-review-2', x: -0.3, y: 0.5 },
            ],
          }),
        })
      } else {
        await route.continue()
      }
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
                    id: 'prediction-review-1',
                    sample_id: 'sample-review-1',
                    predicted_label: 'rose',
                    confidence: 0.91,
                    model_id: modelId,
                    target: 'image_classification',
                    model_version: null,
                    job_id: predictionJobId,
                    created_at: '2026-01-01T00:00:00Z',
                    error: null,
                  },
                  {
                    id: 'prediction-review-2',
                    sample_id: 'sample-review-2',
                    predicted_label: 'tulip',
                    confidence: 0.87,
                    model_id: modelId,
                    target: 'image_classification',
                    model_version: null,
                    job_id: predictionJobId,
                    created_at: '2026-01-01T00:00:00Z',
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

test('runs prediction review flow from /datasets/:id/classify', async ({ page }) => {
  await mockClassifyWorkflowApi(page)

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
  await expect(page.getByRole('button', { name: 'Run Predictions' })).toBeVisible()

  await expect(page.getByRole('radio', { name: 'Grid' })).toBeVisible()
  await expect(page.getByRole('radio', { name: 'List' })).toBeVisible()

  await expect(page.locator('.cs-header__toggle')).toBeVisible()

  await page.waitForSelector('[data-sb-item]')
  const itemCount = await page.locator('[data-sb-item]').count()
  expect(itemCount).toBeGreaterThan(0)

  await expect(page.locator('[data-testid="wafer-map-panel"]')).toBeVisible()
  await expect(page.locator('[data-testid="wafer-map-panel"] canvas')).toBeVisible()
  await expect(page.locator('[data-testid="wafer-map-panel"]')).not.toContainText('No wafer points')

  await page.locator('.n-base-selection').filter({ hasText: 'Select model' }).first().click()
  await page.locator('.n-base-select-option').filter({ hasText: /flower-classifier/ }).click()

  await page.getByRole('button', { name: 'Run Predictions' }).click()

  await expect(page.getByText(/Prediction job submitted:/)).toBeVisible()
  await expect(page.getByText('2 predictions ready for review')).toBeVisible()
  await expect(page.getByText('Prediction Review Mode')).toBeVisible()
  await expect(page.locator('.ag').first()).toContainText('rose')
  await expect(page.locator('.ag').first()).toContainText('tulip')
  await expect(page.getByRole('button', { name: 'Submit 2' })).toBeVisible()
})
