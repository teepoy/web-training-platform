import { req } from "../client/apiClient";

export type TaskType = "classification" | "vqa";
export type DatasetType = "image_classification" | "image_vqa";
export type DatasetStorageMode = "db_full" | "file_shard_sparse";

export interface TaskSpec {
  task_type: TaskType;
  label_space: string[];
  metadata_schema?: Record<string, { type: string; description: string }>;
}

export interface Dataset {
  id: string;
  name: string;
  dataset_type: DatasetType;
  task_spec: TaskSpec;
  created_at: string;
  ls_project_id?: string | null;
  ls_project_url?: string | null;
  org_id?: string;
  org_name?: string;
  is_public?: boolean;
  storage_mode: DatasetStorageMode;
  capabilities?: Record<string, boolean>;
}

export interface DatasetAnnotationStats {
  total_samples: number;
  annotated_samples: number;
  unlabeled_samples: number;
  label_counts: Record<string, number>;
}

export interface CreateDatasetBody {
  name: string;
  dataset_type: string;
  task_spec?: {
    task_type: string;
    label_space: string[];
    metadata_schema?: Record<string, { type: string; description: string }>;
  };
}

export interface ExportFormat {
  format_id: string;
}

export function listDatasets(): Promise<Dataset[]> {
  return req<Dataset[]>("/datasets");
}

export function createDataset(body: CreateDatasetBody): Promise<Dataset> {
  return req<Dataset>("/datasets", {
    method: "POST",
    body: JSON.stringify({
      name: body.name,
      dataset_type: body.dataset_type,
      task_spec: body.task_spec ?? {
        task_type: "classification",
        label_space: [],
      },
    }),
  });
}

export function deleteDataset(id: string): Promise<void> {
  return req<void>(`/datasets/${id}`, { method: "DELETE" });
}

export function getDataset(id: string): Promise<Dataset> {
  return req<Dataset>(`/datasets/${id}`);
}

export function updateLabelSpace(datasetId: string, labelSpace: string[]): Promise<Dataset> {
  return req<Dataset>(`/datasets/${datasetId}/label-space`, {
    method: "PATCH",
    body: JSON.stringify({ label_space: labelSpace }),
  });
}

export function getAnnotationStats(datasetId: string): Promise<DatasetAnnotationStats> {
  return req<DatasetAnnotationStats>(`/datasets/${datasetId}/annotation-stats`);
}

export function listExportFormats(): Promise<ExportFormat[]> {
  return req<ExportFormat[]>("/export-formats");
}

export function toggleDatasetPublic(id: string, isPublic: boolean): Promise<Dataset> {
  return req<Dataset>(`/datasets/${id}/public`, {
    method: "PATCH",
    body: JSON.stringify({ is_public: isPublic }),
  });
}
