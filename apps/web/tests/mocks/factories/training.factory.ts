import type { TrainingJob } from '@/generated/orval/models'

export function makeTrainingJob(overrides?: Partial<TrainingJob>): TrainingJob {
  return {
    id: 'job-e2e-1',
    dataset_id: 'dataset-e2e-1',
    trainer_id: 'trainer-e2e-1',
    status: 'completed',
    created_by: 'user-e2e-1',
    org_id: 'org-e2e-1',
    org_name: 'E2E Org',
    is_public: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    artifact_refs: [],
    ...overrides,
  }
}

export function makeTrainingJobList(overrides?: Partial<TrainingJob>): TrainingJob[] {
  return [makeTrainingJob(overrides)]
}
