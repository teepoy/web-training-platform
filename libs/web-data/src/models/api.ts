import { req } from "../client/apiClient";
import { uploadFile } from "../client/apiClient";

export interface Model {
  id: string;
  uri: string;
  kind: string;
  name: string | null;
  file_size: number | null;
  file_hash: string | null;
  format: string | null;
  created_at: string | null;
  metadata: Record<string, unknown>;
  job_id: string;
  dataset_id: string;
  dataset_name: string;
  preset_name: string;
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

export interface ModelUploadTemplate {
  id: string;
  name: string;
  dataset_types: string[];
  task_types: string[];
  profiles: Array<{
    id: string;
    name: string;
    model_spec: Record<string, string>;
    default_prediction_targets: string[];
  }>;
  label_space_mode: "required" | "forbidden";
  requires_embedding_metadata: boolean;
}

export interface CreateScheduleBody {
  name: string;
  flow_name: string;
  cron: string;
  parameters?: Record<string, unknown>;
  description?: string;
}

export interface UpdateScheduleBody {
  name?: string;
  cron?: string;
  parameters?: Record<string, unknown>;
  description?: string;
  is_schedule_active?: boolean;
}

export interface Schedule {
  id: string;
  name: string;
  flow_name: string;
  cron: string | null;
  parameters: Record<string, unknown>;
  description: string;
  is_schedule_active: boolean;
  created: string | null;
  updated: string | null;
  prefect_deployment_id: string;
}

export interface ScheduleRun {
  id: string;
  name: string;
  deployment_id: string | null;
  flow_name: string | null;
  state_type: string | null;
  state_name: string | null;
  start_time: string | null;
  end_time: string | null;
  total_run_time: number | null;
  parameters: Record<string, unknown>;
}

export function listModels(datasetId?: string, jobId?: string): Promise<Model[]> {
  const params = new URLSearchParams();
  if (datasetId) params.set("dataset_id", datasetId);
  if (jobId) params.set("job_id", jobId);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return req<Model[]>(`/models${qs}`);
}

export function getModel(id: string): Promise<Model> {
  return req<Model>(`/models/${id}`);
}

export function deleteModel(id: string): Promise<void> {
  return req<void>(`/models/${id}`, { method: "DELETE" });
}

export function uploadModel(file: File, metadata: Record<string, unknown>): Promise<Model> {
  const form = new FormData();
  form.append("file", file);
  form.append("metadata", JSON.stringify(metadata));
  return uploadFile<Model>("/models/upload", form);
}

export function listPresets(): Promise<TrainingPreset[]> {
  return req<TrainingPreset[]>("/training-presets");
}

export function getPreset(id: string): Promise<TrainingPreset> {
  return req<TrainingPreset>(`/training-presets/${id}`);
}

export function listModelUploadTemplates(): Promise<ModelUploadTemplate[]> {
  return req<ModelUploadTemplate[]>("/model-upload-templates");
}

export function listSchedules(): Promise<Schedule[]> {
  return req<Schedule[]>("/schedules");
}

export function createSchedule(body: CreateScheduleBody): Promise<Schedule> {
  return req<Schedule>("/schedules", {
    method: "POST",
    body: JSON.stringify({
      name: body.name,
      flow_name: body.flow_name,
      cron: body.cron,
      parameters: body.parameters ?? {},
      description: body.description ?? "",
    }),
  });
}

export function getSchedule(id: string): Promise<Schedule> {
  return req<Schedule>(`/schedules/${id}`);
}

export function updateSchedule(id: string, body: UpdateScheduleBody): Promise<Schedule> {
  return req<Schedule>(`/schedules/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteSchedule(id: string): Promise<void> {
  return req<void>(`/schedules/${id}`, { method: "DELETE" });
}

export function triggerScheduleRun(id: string): Promise<ScheduleRun> {
  return req<ScheduleRun>(`/schedules/${id}/run`, { method: "POST" });
}

export function pauseSchedule(id: string): Promise<Schedule> {
  return req<Schedule>(`/schedules/${id}/pause`, { method: "POST" });
}

export function resumeSchedule(id: string): Promise<Schedule> {
  return req<Schedule>(`/schedules/${id}/resume`, { method: "POST" });
}

export function listScheduleRuns(id: string, limit?: number): Promise<ScheduleRun[]> {
  const qs = limit !== undefined ? `?limit=${limit}` : "";
  return req<ScheduleRun[]>(`/schedules/${id}/runs${qs}`);
}

export interface RunLog {
  id: string | null;
  flow_run_id: string | null;
  level: number;
  timestamp: string;
  message: string;
}

export function getRunLogs(runId: string, limit?: number): Promise<RunLog[]> {
  const qs = limit !== undefined ? `?limit=${limit}` : "";
  return req<RunLog[]>(`/runs/${runId}/logs${qs}`);
}

export type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface ArtifactRef {
  id: string;
  uri: string;
  kind: string;
  metadata: Record<string, unknown>;
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
  org_id?: string;
  org_name?: string;
  is_public?: boolean;
}

export function listJobs(): Promise<TrainingJob[]> {
  return req<TrainingJob[]>("/training-jobs");
}

export function createJob(dataset_id: string, preset_id: string): Promise<TrainingJob> {
  return req<TrainingJob>("/training-jobs", {
    method: "POST",
    body: JSON.stringify({ dataset_id, preset_id }),
  });
}

export function getJob(id: string): Promise<TrainingJob> {
  return req<TrainingJob>(`/training-jobs/${id}`);
}

export function cancelJob(id: string): Promise<{ cancelled: boolean }> {
  return req<{ cancelled: boolean }>(`/training-jobs/${id}/cancel`, { method: "POST" });
}

export function toggleJobPublic(id: string, isPublic: boolean): Promise<TrainingJob> {
  return req<TrainingJob>(`/training-jobs/${id}/public`, {
    method: "PATCH",
    body: JSON.stringify({ is_public: isPublic }),
  });
}
