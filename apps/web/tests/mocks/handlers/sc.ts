import type { Page } from '@playwright/test'
import { create, toBinary } from '@bufbuild/protobuf'
import { WaferMapResponseSchema } from '@/features/sc/generated/proto/sc/v1/sample_pb'

export interface ScInspectionOverrides {
  inspection_time?: string
  wafer_key?: number
  lot_id?: string
  wafer_id?: string
  center_x?: number
  center_y?: number
  origin_x?: number
  origin_y?: number
  die_size_x?: number
  die_size_y?: number
  layer_id?: string
  eqp_id?: string
  recipe_id?: string
  defects?: number
  images?: number
  device?: string
  total?: number
}

export async function mockScInspections(
  page: Page,
  overrides?: ScInspectionOverrides,
): Promise<void> {
  const inspection = {
    inspection_time: overrides?.inspection_time ?? '2026-05-26T08:00:00',
    wafer_key: overrides?.wafer_key ?? 1,
    lot_id: overrides?.lot_id ?? 'LOT-001',
    wafer_id: overrides?.wafer_id ?? 'WAF-001',
    center_x: overrides?.center_x ?? 0,
    center_y: overrides?.center_y ?? 0,
    origin_x: overrides?.origin_x ?? -150000,
    origin_y: overrides?.origin_y ?? -150000,
    die_size_x: overrides?.die_size_x ?? 10000,
    die_size_y: overrides?.die_size_y ?? 10000,
    layer_id: overrides?.layer_id ?? 'LAYER-M1',
    eqp_id: overrides?.eqp_id ?? 'EQ-TOOL-A1',
    recipe_id: overrides?.recipe_id ?? 'RECIPE-001',
    defects: overrides?.defects ?? 50,
    images: overrides?.images ?? 100,
    device: overrides?.device ?? 'DEV-A001',
  }

  await page.route('**/api/v1/sc/inspections*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [inspection],
        total: overrides?.total ?? 1,
      }),
    })
  })
}

export async function mockScInspectionSamples(page: Page): Promise<void> {
  await page.route(
    '**/api/v1/sc/inspections/*/*/samples',
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0 }),
      })
    },
  )
}

export interface ScDatasetOverrides {
  name?: string
  label_space?: string[]
  task_spec?: Record<string, unknown>
}

export async function mockScDataset(
  page: Page,
  datasetId: string,
  overrides?: ScDatasetOverrides,
): Promise<void> {
  const body = {
    id: datasetId,
    name: overrides?.name ?? 'SC Wafer Dataset',
    label_space: overrides?.label_space ?? ['Scratch', 'Particle', 'Pattern Defect'],
    task_spec: overrides?.task_spec ?? { task_type: 'sc' },
  }
  await page.route(`**/api/v1/datasets/${datasetId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
  })
}

export interface ScViewSampleRow {
  sample_id: string
  inspection_time: string
  wafer_key: number
  defect_id: string | number
  wafer_x: number
  wafer_y: number
  rough_bin: number
  class_number: number
  review_images?: Array<{ image_id: number }>
  images?: Array<{
    role: string
    image_id: string
    image_type?: string
    content_type?: string
    url: string
  }>
}

export async function mockScViewSamples(
  page: Page,
  datasetId: string,
  viewType = 'patch_image_v1',
  overrides?: { items?: ScViewSampleRow[]; total?: number },
): Promise<void> {
  const items: ScViewSampleRow[] = overrides?.items ?? [
    {
      sample_id: 'sample-sc-1',
      inspection_time: '2026-05-26T08:00:00',
      wafer_key: 1,
      defect_id: 'defect-001',
      wafer_x: 1000,
      wafer_y: 2000,
      rough_bin: 1,
      class_number: 3,
      review_images: [],
      images: [],
    },
    {
      sample_id: 'sample-sc-2',
      inspection_time: '2026-05-26T08:00:00',
      wafer_key: 1,
      defect_id: 'defect-002',
      wafer_x: 1500,
      wafer_y: 2500,
      rough_bin: 2,
      class_number: 5,
      review_images: [],
      images: [],
    },
  ]
  const body = { items, total: overrides?.total ?? items.length }
  await page.route(
    `**/api/v1/datasets/${datasetId}/views/${viewType}/samples**`,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      })
    },
  )
}

function makeFakePlotPointsBuffer(sampleCount: number): Buffer {
  const pts = Array.from({ length: sampleCount * 6 }, (_, i) => i % 100)
  const msg = create(WaferMapResponseSchema, {
    total: sampleCount,
    waferPoints: pts,
    diePoints: pts,
  })
  return Buffer.from(toBinary(WaferMapResponseSchema, msg))
}

export async function mockScPlotPoints(
  page: Page,
  datasetId: string,
  sampleCount = 1000,
): Promise<void> {
  const body = makeFakePlotPointsBuffer(sampleCount)
  await page.route(
    `**/api/v1/sc/datasets/${datasetId}/plot-points/stream**`,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: [
          'event: progress\ndata: {"event_type":"progress","operation":"sc.plot-points","status":"loading","message":"Preparing plot points"}\n\n',
          'event: done\ndata: {"event_type":"done"}\n\n',
        ].join(''),
      })
    },
  )
  await page.route(
    `**/api/v1/sc/datasets/${datasetId}/plot-points**`,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/x-protobuf',
        body,
      })
    },
  )
}

export async function mockScDefectIds(
  page: Page,
  datasetId: string,
  total = 1000,
): Promise<void> {
  const body = Buffer.alloc(total * 4)
  for (let index = 0; index < total; index += 1) {
    body.writeInt32LE(index + 1, index * 4)
  }
  await page.route(
    `**/api/v1/sc/datasets/${datasetId}/defect-ids.bin**`,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/octet-stream',
        body,
      })
    },
  )
}

export async function mockScViewSamplesPaged(
  page: Page,
  datasetId: string,
  viewType = 'patch_image_v1',
  total = 1000,
  pageSize = 200,
): Promise<void> {
  await page.route(
    `**/api/v1/datasets/${datasetId}/views/${viewType}/samples**`,
    async (route) => {
      const url = new URL(route.request().url())
      const offset = parseInt(url.searchParams.get('offset') ?? '0', 10)
      const limit = parseInt(url.searchParams.get('limit') ?? String(pageSize), 10)
      const items = Array.from({ length: Math.min(limit, Math.max(0, total - offset)) }, (_, i) => ({
        sample_id: `s-${offset + i}`,
        inspection_time: '2026-01-01T00:00:00',
        wafer_key: 1,
        defect_id: String(offset + i + 1),
        wafer_x: (offset + i) * 100,
        wafer_y: (offset + i) * 200,
        die_x: (offset + i) % 10,
        die_y: (offset + i) % 8,
        rough_bin: (offset + i) % 5,
        class_number: (offset + i) % 3,
        review_images: [],
        images: [],
      }))
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items, total }),
      })
    },
  )
}

export async function mockScSamplesWithLabels(
  page: Page,
  datasetId: string,
  total = 1000,
  pageSize = 200,
): Promise<void> {
  await page.route(
    `**/api/v1/datasets/${datasetId}/samples-with-labels**`,
    async (route) => {
      const url = new URL(route.request().url())
      const offset = parseInt(url.searchParams.get('offset') ?? '0', 10)
      const limit = parseInt(url.searchParams.get('limit') ?? String(pageSize), 10)
      const items = Array.from({ length: Math.min(limit, Math.max(0, total - offset)) }, (_, i) => ({
        id: `s-${offset + i}`,
        latest_annotation: null,
      }))
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items, total }),
      })
    },
  )
}
