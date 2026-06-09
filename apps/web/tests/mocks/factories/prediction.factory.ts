import type {
  PredictionJobResponse,
  PredictionResultResponse,
  ModelResponse,
} from '@/generated/orval/models'

export function makePredictionJob(overrides?: Partial<PredictionJobResponse>): PredictionJobResponse {
  return {
    id: 'prediction-job-1',
    dataset_id: 'dataset-e2e-1',
    model_id: 'model-e2e-1',
    status: 'queued',
    created_by: 'user-e2e-1',
    target: 'image_classification',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

export function makePredictionResult(
  sampleId: string,
  modelId: string,
  jobId: string,
  overrides?: Partial<PredictionResultResponse>,
): PredictionResultResponse {
  return {
    sample_id: sampleId,
    predicted_label: 'rose',
    confidence: 0.91,
    model_id: modelId,
    target: 'image_classification',
    job_id: jobId,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

export function makeModel(overrides?: Partial<ModelResponse>): ModelResponse {
  return {
    id: 'model-e2e-1',
    uri: 'memory://models/model-e2e-1',
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
    job_id: 'job-e2e-1',
    dataset_id: 'dataset-e2e-1',
    dataset_name: 'flowers-dataset',
    trainer_name: 'resnet50-cls-v1',
    ...overrides,
  }
}
