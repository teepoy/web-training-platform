import { req, uploadFile, getApiBase } from "./client";
import type {
  Model,
  ModelUploadTemplate,
  UploadModelMetadata,
} from "./types";

export function listModels(
  datasetId?: string,
  jobId?: string,
): Promise<Model[]> {
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

export function downloadModelUrl(id: string): string {
  return `${getApiBase()}/models/${id}/download`;
}

export function uploadModel(
  file: File,
  metadata: UploadModelMetadata,
): Promise<Model> {
  const form = new FormData();
  form.append("file", file);
  form.append("metadata", JSON.stringify(metadata));
  return uploadFile<Model>("/models/upload", form);
}

export function listModelUploadTemplates(): Promise<ModelUploadTemplate[]> {
  return req<ModelUploadTemplate[]>("/model-upload-templates");
}
