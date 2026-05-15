import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

const listSamplesWithLabelsMock = vi.fn()
const fetchSampleSliceMock = vi.fn()

vi.mock('@platform/web-ui/api/samples', () => ({
  listSamplesWithLabels: (...args: unknown[]) => listSamplesWithLabelsMock(...args),
}))

vi.mock('@platform/web-ui/api/datasets', () => ({
  fetchSampleSlice: (...args: unknown[]) => fetchSampleSliceMock(...args),
}))

import { useSampleLoader } from './useSampleLoader'
import type { SampleWithLabels } from '@platform/web-ui/api/samples'

function makeSample(id: string): SampleWithLabels {
  return {
    id,
    dataset_id: 'ds-1',
    image_uris: [],
    metadata: {},
    latest_annotation: null,
  }
}

function flush(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

describe('useSampleLoader', () => {
  beforeEach(() => {
    listSamplesWithLabelsMock.mockReset()
    fetchSampleSliceMock.mockReset()
  })

  it('uses listSamplesWithLabels when no sampleIds are provided', async () => {
    listSamplesWithLabelsMock.mockResolvedValue({
      items: [makeSample('a'), makeSample('b')],
      total: 2,
    })

    const loader = useSampleLoader({ datasetId: 'ds-1', pageSize: 100 })
    await loader.loadMore()

    expect(listSamplesWithLabelsMock).toHaveBeenCalledTimes(1)
    expect(listSamplesWithLabelsMock).toHaveBeenCalledWith('ds-1', 0, 100, undefined, 'id')
    expect(fetchSampleSliceMock).not.toHaveBeenCalled()
    expect(loader.samples.value.map((s) => s.id)).toEqual(['a', 'b'])
    expect(loader.totalCount.value).toBe(2)
  })

  it('uses fetchSampleSlice when sampleIds are non-empty', async () => {
    fetchSampleSliceMock.mockResolvedValue({
      items: [makeSample('x'), makeSample('y')],
      total: 2,
    })

    const sampleIds = ref<string[] | null>(['x', 'y'])
    const loader = useSampleLoader({ datasetId: 'ds-1', pageSize: 50, sampleIds })
    await loader.loadMore()

    expect(fetchSampleSliceMock).toHaveBeenCalledTimes(1)
    expect(fetchSampleSliceMock).toHaveBeenCalledWith('ds-1', {
      offset: 0,
      limit: 50,
      label: null,
      orderBy: 'id',
      sampleIds: ['x', 'y'],
    })
    expect(listSamplesWithLabelsMock).not.toHaveBeenCalled()
    expect(loader.samples.value.map((s) => s.id)).toEqual(['x', 'y'])
  })

  it('treats null and empty sampleIds as the same no-scope state', async () => {
    listSamplesWithLabelsMock.mockResolvedValue({ items: [makeSample('a')], total: 1 })

    const sampleIds = ref<string[] | null>([])
    const loader = useSampleLoader({ datasetId: 'ds-1', pageSize: 100, sampleIds })
    await loader.loadMore()

    expect(listSamplesWithLabelsMock).toHaveBeenCalledTimes(1)
    expect(fetchSampleSliceMock).not.toHaveBeenCalled()

    sampleIds.value = null
    await flush()
    await flush()

    expect(fetchSampleSliceMock).not.toHaveBeenCalled()
  })

  it('resets and refetches when sampleIds change', async () => {
    listSamplesWithLabelsMock.mockResolvedValue({
      items: [makeSample('a'), makeSample('b')],
      total: 2,
    })

    const sampleIds = ref<string[] | null>(null)
    const loader = useSampleLoader({ datasetId: 'ds-1', pageSize: 100, sampleIds })
    await loader.loadMore()
    expect(loader.samples.value.map((s) => s.id)).toEqual(['a', 'b'])

    fetchSampleSliceMock.mockResolvedValue({
      items: [makeSample('z')],
      total: 1,
    })
    sampleIds.value = ['z']
    await flush()
    await flush()

    expect(fetchSampleSliceMock).toHaveBeenCalledTimes(1)
    expect(loader.samples.value.map((s) => s.id)).toEqual(['z'])
    expect(loader.totalCount.value).toBe(1)
  })

  it('switches back to default pagination when sampleIds clears', async () => {
    fetchSampleSliceMock.mockResolvedValue({ items: [makeSample('z')], total: 1 })
    const sampleIds = ref<string[] | null>(['z'])
    const loader = useSampleLoader({ datasetId: 'ds-1', pageSize: 100, sampleIds })
    await loader.loadMore()
    expect(loader.samples.value.map((s) => s.id)).toEqual(['z'])

    listSamplesWithLabelsMock.mockResolvedValue({
      items: [makeSample('a'), makeSample('b')],
      total: 2,
    })
    sampleIds.value = null
    await flush()
    await flush()

    expect(listSamplesWithLabelsMock).toHaveBeenCalledTimes(1)
    expect(loader.samples.value.map((s) => s.id)).toEqual(['a', 'b'])
  })
})
