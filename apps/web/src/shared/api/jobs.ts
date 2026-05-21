import { req } from "./client";
import type {
  TrainingPreset,
  TrainingJob,
  CancelJobResponse,
  MarkLeftResponse,
} from "./types";

export function listJobs(): Promise<TrainingJob[]> {
  return req<TrainingJob[]>("/training-jobs");
}

export function createJob(
  dataset_id: string,
  preset_id: string,
): Promise<TrainingJob> {
  return req<TrainingJob>("/training-jobs", {
    method: "POST",
    body: JSON.stringify({ dataset_id, preset_id }),
  });
}

export function getJob(id: string): Promise<TrainingJob> {
  return req<TrainingJob>(`/training-jobs/${id}`);
}

export function cancelJob(id: string): Promise<CancelJobResponse> {
  return req<CancelJobResponse>(`/training-jobs/${id}/cancel`, {
    method: "POST",
  });
}

export function markJobLeft(id: string): Promise<MarkLeftResponse> {
  return req<MarkLeftResponse>(`/training-jobs/${id}/mark-left`, {
    method: "POST",
  });
}

export function toggleJobPublic(
  id: string,
  isPublic: boolean,
): Promise<TrainingJob> {
  return req<TrainingJob>(`/training-jobs/${id}/public`, {
    method: "PATCH",
    body: JSON.stringify({ is_public: isPublic }),
  });
}

export function listPresets(): Promise<TrainingPreset[]> {
  return req<TrainingPreset[]>("/training-presets");
}

export function getPreset(id: string): Promise<TrainingPreset> {
  return req<TrainingPreset>(`/training-presets/${id}`);
}
