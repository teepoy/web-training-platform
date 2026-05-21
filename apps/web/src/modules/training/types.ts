export type ModelFramework = "pytorch" | "dspy";

export type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface TrainingEvent {
  job_id: string;
  ts: string;
  level: string;
  message: string;
  payload: Record<string, unknown>;
}

export interface ArtifactRef {
  id: string | null;
  uri: string;
  kind: string;
  metadata: Record<string, unknown>;
  name?: string | null;
  file_size?: number | null;
  file_hash?: string | null;
  format?: string | null;
  created_at?: string | null;
}

export interface TrainingJob {
  id: string;
  dataset_id: string;
  preset_id: string;
  status: JobStatus;
  created_by: string;
  created_at: string;
  updated_at: string;
  artifact_refs: ArtifactRef[];
  external_job_id?: string | null;
  org_id?: string;
  org_name?: string;
  is_public?: boolean;
}

export interface TrainingPreset {
  id: string;
  name: string;
  version?: string;
  description?: string;
  tags?: string[];
  deprecated?: boolean;
  trainable?: boolean;
  model: {
    framework: string;
    base_model: string;
    source?: string | null;
    checkpoint?: string | null;
  };
  train: {
    process: string;
    dataloader?: { ref: string } | null;
    hyperparams?: Record<string, unknown>;
  };
  predict: {
    targets: Record<string, { process: string; label_space?: string[] | null; threshold?: number | null }>;
  };
  test?: Record<string, unknown> | null;
  convert?: Record<string, unknown> | null;
  runtime: {
    gpu?: boolean;
    min_vram_gb?: number | null;
    env?: Record<string, string>;
    queue?: string | null;
  };
  compatibility?: {
    dataset_types: string[];
    task_types: string[];
    prediction_targets: string[];
  };
  model_spec?: { architecture: string; num_classes: number } | { framework: string; base_model: string };
  omegaconf_yaml?: string;
  dataloader_ref?: string;
  org_id?: string | null;
}

export interface CancelJobResponse {
  cancelled: boolean;
}

export interface MarkLeftResponse {
  marked: boolean;
}
