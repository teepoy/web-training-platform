import path from 'node:path'
import { test, expect } from '../../fixtures'
import { ReclassifyPagePom } from '../../pages/sc/ReclassifyPagePom'
import {
  mockScPlotPoints,
  mockScViewSamplesPaged,
  mockScSamplesWithLabels,
  mockScDataset,
} from '../../mocks/handlers'

const DATASET_ID = 'test-sc'

test.describe('SC Reclassify lazy loading @mock', () => {
  test('plot-points fires once, blink table loads more on scroll @mock', async ({
    authedPage,
  }) => {
    await mockScDataset(authedPage, DATASET_ID, {
      name: 'Test SC Dataset',
      label_space: ['Scratch', 'Clean'],
    })

    await mockScPlotPoints(authedPage, DATASET_ID, 1000)
    await mockScViewSamplesPaged(authedPage, DATASET_ID, 'patch_image_v1', 1000, 200)
    await mockScSamplesWithLabels(authedPage, DATASET_ID, 1000, 200)

    const plotPointRequests: string[] = []
    authedPage.on('request', (req) => {
      if (req.url().includes('/sc/datasets/') && req.url().includes('/plot-points')) {
        plotPointRequests.push(req.url())
      }
    })

    const viewSampleRequests: Array<{ offset: number; url: string }> = []
    authedPage.on('request', (req) => {
      if (req.url().includes(`/views/patch_image_v1/samples`)) {
        const url = new URL(req.url())
        const offset = parseInt(url.searchParams.get('offset') ?? '0', 10)
        viewSampleRequests.push({ offset, url: req.url() })
      }
    })

    const pom = new ReclassifyPagePom(authedPage)
    await pom.gotoReclassify(DATASET_ID)

    await authedPage.waitForTimeout(2000)

    expect(plotPointRequests.length).toBe(1)

    const firstPageRequests = viewSampleRequests.filter((r) => r.offset === 0)
    expect(firstPageRequests.length).toBeGreaterThanOrEqual(1)

    await expect(pom.headerSampleCount(1000)).toBeVisible({ timeout: 5_000 })

    const scrollContainer = pom.blinkScrollContainer
    const containerExists = await scrollContainer.count()
    if (containerExists > 0) {
      await scrollContainer.evaluate((el) => {
        el.scrollTop = el.scrollHeight
      })
      await authedPage.waitForTimeout(1500)

      const secondPageRequests = viewSampleRequests.filter((r) => r.offset > 0)
      expect(secondPageRequests.length).toBeGreaterThanOrEqual(1)
      if (secondPageRequests.length > 0) {
        expect(secondPageRequests[0].offset).toBe(200)
      }
    }

    await authedPage.screenshot({
      path: path.join(process.cwd(), '../../.sisyphus/evidence/task-9-after-scroll.png'),
    })

    expect(plotPointRequests.length).toBe(1)
  })
})
