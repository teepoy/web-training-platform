import type {
  Annotation,
  ArtifactRef,
  Dataset,
  PaginatedResponse,
  PredictionEdit,
  PredictionResult,
  Sample,
  TrainingJob,
  TrainingPreset,
  UploadResponse,
  UpdateAnnotationPayload,
} from "./types";
import type { ApiError as ApiErrorType } from "./types";
import { useAuthStore } from "./stores/auth";

export const API_BASE = import.meta.env.VITE_API_BASE || "/api/v1";

// ---------------------------------------------------------------------------
// Typed error class
// ---------------------------------------------------------------------------

export class ApiError extends Error implements ApiErrorType {
  detail: string;
  status: number;

  constructor(detail: string, status: number) {
    super(`API ${status}: ${detail}`);
    this.detail = detail;
    this.status = status;
  }
}

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

async function req<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = 30_000
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  // Auth header injection — no-op when token is null (scaffold)
  let authHeader: Record<string, string> = {};
  try {
    const authStore = useAuthStore();
    if (authStore.token) {
      authHeader = { Authorization: `Bearer ${authStore.token}` };
    }
  } catch {
    // Pinia not yet active (e.g. called outside Vue context) — skip auth
  }

  try {
    const r = await fetch(`${API_BASE}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...authHeader,
        ...(init?.headers ?? {}),
      },
      signal: controller.signal,
      ...init,
    });

    if (!r.ok) {
      let detail = `request failed: ${r.status}`;
      try {
        const body = await r.json();
        detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
      } catch {
        // response body not JSON — keep default message
      }
      throw new ApiError(detail, r.status);
    }

    // 204/205 No Content — return undefined without calling r.json() (would throw SyntaxError)
    if (r.status === 204 || r.status === 205) {
      return undefined as T;
    }
    return (await r.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

// ---------------------------------------------------------------------------
// Multipart upload (bypasses req<T> to avoid forcing JSON Content-Type)
// ---------------------------------------------------------------------------

export async function uploadSampleImage(sampleId: string, file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const r = await fetch(`${API_BASE}/samples/${sampleId}/upload`, {
    method: "POST",
    body: form,
  });
  if (!r.ok) {
    let detail = `upload failed: ${r.status}`;
    try {
      const body = await r.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
    } catch { /* ignore */ }
    throw new ApiError(detail, r.status);
  }
  return r.json() as Promise<UploadResponse>;
}

// ---------------------------------------------------------------------------
// Request body interfaces
// ---------------------------------------------------------------------------

export interface CreateDatasetBody {
  name: string;
  task_spec?: { task_type: string; label_space: string[] };
}

export interface CreateSampleBody {
  image_uris: string[];
  metadata?: Record<string, unknown>;
}

export interface CreateAnnotationBody {
  sample_id: string;
  label: string;
  created_by?: string;
}

export interface CreatePresetBody {
  name: string;
  model_spec: { architecture: string; num_classes: number };
  omegaconf_yaml: string;
  dataloader_ref?: string;
}

export interface CreateJobBody {
  dataset_id: string;
  preset_id: string;
  created_by?: string;
}

export interface CreatePredictionBody {
  sample_id: string;
  predicted_label: string;
  score: number;
  model_artifact_id: string;
}

export interface EditPredictionBody {
  corrected_label: string;
  edited_by?: string;
}

// ---------------------------------------------------------------------------
// Export/feature-op response shapes
// ---------------------------------------------------------------------------

export interface DatasetExport {
  dataset: Dataset;
  samples: Sample[];
  annotations: Annotation[];
}

export interface PersistExportResponse {
  uri: string;
}

export interface ExtractFeaturesResponse {
  count: number;
  embedding_model: string;
  status: string;
}

export interface SimilarityResponse {
  sample_id: string;
  neighbors: Array<{ sample_id: string; score: number }>;
}

export interface SelectionMetricsResponse {
  uniqueness: Record<string, number>;
  representativeness: Record<string, number>;
}

export interface UncoveredHintsResponse {
  dataset_id?: string;
  clusters: Array<{ cluster_id: string; size: number; hint: string }>;
}

export interface CancelJobResponse {
  cancelled: boolean;
}

export interface MarkLeftResponse {
  marked: boolean;
}

export interface JobMetricsResponse {
  metrics: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// API surface
// ---------------------------------------------------------------------------

export const api = {
  // ---- Datasets ----
  listDatasets: () => req<Dataset[]>("/datasets"),

  createDataset: (body: CreateDatasetBody) =>
    req<Dataset>("/datasets", {
      method: "POST",
      body: JSON.stringify({
        name: body.name,
        task_spec: body.task_spec ?? { task_type: "classification", label_space: [] },
      }),
    }),

  getDataset: (id: string) => req<Dataset>(`/datasets/${id}`),

  // ---- Samples ----
  listSamples: (datasetId: string, offset?: number, limit?: number) => {
    const params = new URLSearchParams();
    if (offset !== undefined) params.set("offset", String(offset));
    if (limit !== undefined) params.set("limit", String(limit));
    const qs = params.toString() ? `?${params.toString()}` : "";
    return req<PaginatedResponse<Sample>>(`/datasets/${datasetId}/samples${qs}`);
  },

  createSample: (datasetId: string, body: CreateSampleBody) =>
    req<Sample>(`/datasets/${datasetId}/samples`, {
      method: "POST",
      body: JSON.stringify({ image_uris: body.image_uris, metadata: body.metadata ?? {} }),
    }),

  getSample: (sampleId: string) => req<Sample>(`/samples/${sampleId}`),

  // ---- Annotations ----
  createAnnotation: (body: CreateAnnotationBody) =>
    req<Annotation>("/annotations", {
      method: "POST",
      body: JSON.stringify({
        sample_id: body.sample_id,
        label: body.label,
        created_by: body.created_by ?? "web-user",
      }),
    }),

  // ---- Training Presets ----
  listPresets: () => req<TrainingPreset[]>("/training-presets"),

  createPreset: (body: CreatePresetBody) =>
    req<TrainingPreset>("/training-presets", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getPreset: (id: string) => req<TrainingPreset>(`/training-presets/${id}`),

  // ---- Training Jobs ----
  listJobs: () => req<TrainingJob[]>("/training-jobs"),

  createJob: (dataset_id: string, preset_id: string) =>
    req<TrainingJob>("/training-jobs", {
      method: "POST",
      body: JSON.stringify({ dataset_id, preset_id, created_by: "web-user" }),
    }),

  getJob: (id: string) => req<TrainingJob>(`/training-jobs/${id}`),

  cancelJob: (id: string) =>
    req<CancelJobResponse>(`/training-jobs/${id}/cancel`, { method: "POST" }),

  markJobLeft: (id: string) =>
    req<MarkLeftResponse>(`/training-jobs/${id}/mark-left`, { method: "POST" }),

  // Job metrics — placeholder (endpoint may not exist yet)
  getJobMetrics: (jobId: string) =>
    req<JobMetricsResponse>(`/training-jobs/${jobId}/metrics`),

  // ---- Predictions ----
  listPredictions: () => req<PredictionResult[]>("/predictions"),

  createPrediction: (body: CreatePredictionBody) =>
    req<PredictionResult>("/predictions", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  editPrediction: (id: string, body: EditPredictionBody) =>
    req<PredictionEdit>(`/predictions/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ corrected_label: body.corrected_label, edited_by: body.edited_by ?? "web-user" }),
    }),

  // ---- Exports ----
  getExport: (datasetId: string) =>
    req<DatasetExport>(`/exports/${datasetId}`),

  persistExport: (datasetId: string) =>
    req<PersistExportResponse>(`/exports/${datasetId}/persist`, { method: "POST" }),

  // ---- Feature Ops ----
  extractFeatures: (datasetId: string, force?: boolean) => {
    const qs = force ? "?force=true" : "";
    return req<ExtractFeaturesResponse>(`/datasets/${datasetId}/features/extract${qs}`, { method: "POST" });
  },

  getSimilarity: (datasetId: string, sampleId: string, k?: number) => {
    const qs = k !== undefined ? `?k=${k}` : "";
    return req<SimilarityResponse>(`/datasets/${datasetId}/similarity/${sampleId}${qs}`);
  },

  getSelectionMetrics: (datasetId: string) =>
    req<SelectionMetricsResponse>(`/datasets/${datasetId}/selection-metrics`),

  getUncoveredHints: (datasetId: string) =>
    req<UncoveredHintsResponse>(`/datasets/${datasetId}/hints/uncovered`),

  getEmbedConfig: (datasetId: string) =>
    req<Record<string, unknown>>(`/datasets/${datasetId}/embed-config`),

  updateEmbedConfig: (datasetId: string, config: { model: string; dimension: number }) =>
    req<Record<string, unknown>>(`/datasets/${datasetId}/embed-config`, {
      method: "PATCH",
      body: JSON.stringify(config),
    }),

  // ---- Artifacts (Wave 2 placeholders) ----
  downloadArtifact: (id: string) =>
    req<ArtifactRef>(`/artifacts/${id}/download`),

  // ---- Image Upload ----
  uploadSampleImage: (sampleId: string, file: File) => uploadSampleImage(sampleId, file),

  // ---- Annotation CRUD (new) ----
  listAnnotationsForSample: (sampleId: string) =>
    req<Annotation[]>(`/samples/${sampleId}/annotations`),

  updateAnnotation: (annotationId: string, payload: UpdateAnnotationPayload) =>
    req<Annotation>(`/annotations/${annotationId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  deleteAnnotation: (annotationId: string) =>
    req<void>(`/annotations/${annotationId}`, { method: "DELETE" }),
};

// ---------------------------------------------------------------------------
// SSE helper
// ---------------------------------------------------------------------------

export function buildJobEventSource(jobId: string): EventSource {
  return new EventSource(`${API_BASE}/training-jobs/${jobId}/events`);
}
