import path from 'node:path'
import { test, expect } from '../../fixtures'
import { ReclassifyPagePom } from '../../pages/sc/ReclassifyPagePom'
import {
  mockScDefectIds,
  mockScPlotPoints,
  mockScViewSamplesPaged,
  mockScSamplesWithLabels,
  mockScDataset,
} from '../../mocks/handlers'

const DATASET_ID = 'test-sc'

test.describe('SC Reclassify warmup and sidebar @mock', () => {
  test('warmup gates protobuf, defect ids, and sample requests @mock', async ({
    authedPage,
  }) => {
    await mockScDataset(authedPage, DATASET_ID, {
      name: 'Test SC Dataset',
      label_space: ['Scratch', 'Clean'],
    })

    await mockScPlotPoints(authedPage, DATASET_ID, 1000)
    await mockScDefectIds(authedPage, DATASET_ID, 1000)
    await mockScViewSamplesPaged(authedPage, DATASET_ID, 'patch_image_v1', 1000, 200)
    await mockScSamplesWithLabels(authedPage, DATASET_ID, 1000, 200)

    const requestEvents: string[] = []
    authedPage.on('request', (req) => {
      const url = req.url()
      if (url.includes(`/api/v1/sc/datasets/${DATASET_ID}/plot-points/stream`)) {
        requestEvents.push('plot-points-stream')
      } else if (url.includes(`/api/v1/sc/datasets/${DATASET_ID}/plot-points`)) {
        requestEvents.push('plot-points-protobuf')
      } else if (url.includes(`/api/v1/sc/datasets/${DATASET_ID}/defect-ids.bin`)) {
        requestEvents.push('defect-ids')
      } else if (url.includes(`/api/v1/datasets/${DATASET_ID}/views/patch_image_v1/samples`)) {
        requestEvents.push('view-samples')
      }
    })

    const viewSampleRequests: Array<{ offset: number; url: string }> = []
    authedPage.on('request', (req) => {
      if (req.url().includes(`/views/patch_image_v1/samples`)) {
        const url = new URL(req.url())
        const offset = parseInt(url.searchParams.get('offset') ?? '0', 10)
        viewSampleRequests.push({
          offset,
          url: req.url(),
        })
      }
    })

    const pom = new ReclassifyPagePom(authedPage)
    await pom.gotoReclassify(DATASET_ID)

    await authedPage.waitForTimeout(2000)

    expect(requestEvents.filter((event) => event === 'plot-points-stream')).toHaveLength(1)
    expect(requestEvents.filter((event) => event === 'plot-points-protobuf')).toHaveLength(1)
    const warmupIndex = requestEvents.indexOf('plot-points-stream')
    expect(warmupIndex).toBeGreaterThanOrEqual(0)
    for (const event of ['plot-points-protobuf', 'defect-ids', 'view-samples']) {
      const eventIndex = requestEvents.indexOf(event)
      expect(eventIndex).toBeGreaterThan(warmupIndex)
    }

    const firstPageRequests = viewSampleRequests.filter((r) => r.offset === 0)
    expect(firstPageRequests.length).toBeGreaterThanOrEqual(1)

    await expect(pom.headerSampleCount(200)).toBeVisible({ timeout: 5_000 })

    await authedPage.screenshot({
      path: path.join(process.cwd(), '../../.sisyphus/evidence/task-9-after-scroll.png'),
    })

    expect(requestEvents.filter((event) => event === 'plot-points-stream')).toHaveLength(1)
    expect(requestEvents.filter((event) => event === 'plot-points-protobuf')).toHaveLength(1)
  })

  test('reclassify sidebar exposes code/name labels and custom shortcuts @mock', async ({
    authedPage,
  }) => {
    await mockScDataset(authedPage, DATASET_ID, {
      name: 'Test SC Dataset',
      label_space: [],
    })

    await mockScPlotPoints(authedPage, DATASET_ID, 24)
    await mockScDefectIds(authedPage, DATASET_ID, 24)
    await mockScViewSamplesPaged(authedPage, DATASET_ID, 'patch_image_v1', 24, 24)
    await mockScSamplesWithLabels(authedPage, DATASET_ID, 24, 24)

    const pom = new ReclassifyPagePom(authedPage)
    await pom.gotoReclassify(DATASET_ID)

    await expect(authedPage.getByTestId('reclassify-code-row-0')).toContainText('Code 0')
    await expect(authedPage.getByTestId('reclassify-code-row-60')).toContainText('Code 60')

    await authedPage.getByTestId('reclassify-new-label-input').locator('input').fill('Bridge')
    await authedPage.getByTestId('reclassify-add-label-button').click()

    await expect(authedPage.getByTestId('reclassify-code-row-61')).toContainText('Bridge')

    const shortcutInput = authedPage.getByTestId('reclassify-shortcut-input-61').locator('input')
    await shortcutInput.fill('q')
    await expect(shortcutInput).toHaveValue('q')
  })
})
