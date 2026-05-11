export const predictionKeys = {
  all: ["predictions"] as const,
  jobs: ["predictions", "jobs"] as const,
  job: (id: string) => ["predictions", "job", id] as const,
  jobPredictions: (id: string) => ["predictions", "job-predictions", id] as const,
  reviews: (datasetId: string) => ["predictions", "reviews", datasetId] as const,
  review: (actionId: string) => ["predictions", "review", actionId] as const,
  collections: (datasetId: string) => ["predictions", "collections", datasetId] as const,
};
