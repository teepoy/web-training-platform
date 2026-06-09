import type { SampleWithLabels } from '@/generated/orval/models'

/**
 * Single sample factory with sensible classification defaults.
 */
export function makeSample(
  datasetId: string,
  index: number,
  overrides?: Partial<SampleWithLabels>,
): SampleWithLabels {
  const i = index + 1
  return {
    id: `sample-${i}`,
    dataset_id: datasetId,
    image_uris: [`memory://sample-${i}.png`],
    metadata: { split: 'val' },
    latest_annotation: null,
    ...overrides,
  }
}

/**
 * Generates an array of {@link count} samples for virtualization /
 * bulk-list tests.
 */
export function makeSamples(
  datasetId: string,
  count: number,
  overrides?: Partial<SampleWithLabels>,
): SampleWithLabels[] {
  return Array.from({ length: count }, (_, i) => makeSample(datasetId, i, overrides))
}
