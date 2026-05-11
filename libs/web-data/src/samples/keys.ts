export const sampleKeys = {
  all: ["samples"] as const,
  list: (datasetId: string, filters?: Record<string, unknown>) =>
    ["samples", "list", datasetId, filters ?? {}] as const,
  detail: (sampleId: string) => ["samples", "detail", sampleId] as const,
  annotations: (sampleId: string) => ["samples", "annotations", sampleId] as const,
  similarity: (datasetId: string, sampleId: string, k?: number) =>
    ["samples", "similarity", datasetId, sampleId, k ?? 5] as const,
};
