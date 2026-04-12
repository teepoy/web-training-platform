import type {
  Annotation,
  AnnotationVersion,
  BulkCreateSampleItem,
  BulkCreateSampleResponse,
  BulkAnnotationRequest,
  BulkAnnotationResponse,
  DashboardResponse,
  Dataset,
  DatasetAnnotationStats,
  CreatePredictionCollectionRequest,
  ExportFormat,
  LoginResponse,
  Model,
  ModelUploadTemplate,
  Organization,
  PaginatedResponse,
  PredictionEvent,
  PredictionCollection,
  PredictionJob,
  PredictionResult,
  PredictSingleRequest,
  ReviewAction,
  RunLog,
  RunPredictionRequest,
  Sample,
  SampleWithLabels,
  SaveReviewAnnotationItem,
  SaveReviewAnnotationsResponse,
  Schedule,
  ScheduleRun,
  SyncResult,
  SyncPredictionCollectionResponse,
  TaskTrackerDetail,
  TaskTrackerSummary,
  TrainingJob,
  TrainingPreset,
  UploadResponse,
  UploadModelMetadata,
  UpdateAnnotationPayload,
  User,
  UserWithOrgs,
  VersionExportResponse,
} from "./types";
import type { ApiError as ApiErrorType } from "./types";
import { getStoredToken, useAuthStore } from "./stores/auth";

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

  let authHeader: Record<string, string> = {};
  let hasAuthToken = false;
  try {
    const authStore = useAuthStore();
    const token = authStore.token ?? getStoredToken();
    if (token) {
      authHeader["Authorization"] = `Bearer ${token}`;
      hasAuthToken = true;
    }
  } catch {
  }

  try {
    const { useOrgStore } = await import("./stores/org");
    const orgStore = useOrgStore();
    if (orgStore.currentOrgId) {
      authHeader["X-Organization-ID"] = orgStore.currentOrgId;
    }
  } catch {
  }

  try {
    const { headers: initHeaders, ...restInit } = init ?? {};
    const r = await fetch(`${API_BASE}${path}`, {
      ...restInit,
      headers: {
        "Content-Type": "application/json",
        ...authHeader,
        ...((initHeaders as Record<string, string>) ?? {}),
      },
      signal: controller.signal,
    });

    if (!r.ok) {
      if (r.status === 401 && hasAuthToken) {
        try {
          const authStore = useAuthStore();
          authStore.logout();
        } catch {
          /* ignore */
        }
        try {
          const { router } = await import("./router");
          router.push("/login");
        } catch {
          /* ignore */
        }
      }
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
  const uploadHeaders: Record<string, string> = {};
  try {
    const authStore = useAuthStore();
    const token = authStore.token ?? getStoredToken();
    if (token) {
      uploadHeaders["Authorization"] = `Bearer ${token}`;
    }
  } catch {
    /* ignore */
  }
  try {
    const { useOrgStore } = await import("./stores/org");
    const orgStore = useOrgStore();
    if (orgStore.currentOrgId) {
      uploadHeaders["X-Organization-ID"] = orgStore.currentOrgId;
    }
  } catch {
    /* ignore */
  }
  const r = await fetch(`${API_BASE}/samples/${sampleId}/upload`, {
    method: "POST",
    headers: uploadHeaders,
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
// Model upload (multipart)
// ---------------------------------------------------------------------------

export async function uploadModel(
  file: File,
  metadata: UploadModelMetadata,
): Promise<Model> {
  const form = new FormData();
  form.append("file", file);
  const uploadHeaders: Record<string, string> = {};
  try {
    const authStore = useAuthStore();
    if (authStore.token) {
      uploadHeaders["Authorization"] = `Bearer ${authStore.token}`;
    }
  } catch {
    /* ignore */
  }
  try {
    const { useOrgStore } = await import("./stores/org");
    const orgStore = useOrgStore();
    if (orgStore.currentOrgId) {
      uploadHeaders["X-Organization-ID"] = orgStore.currentOrgId;
    }
  } catch {
    /* ignore */
  }
  form.append("metadata", JSON.stringify(metadata));
  const r = await fetch(`${API_BASE}/models/upload`, {
    method: "POST",
    headers: uploadHeaders,
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
  return r.json() as Promise<Model>;
}

// ---------------------------------------------------------------------------
// Request body interfaces
// ---------------------------------------------------------------------------

export interface CreateDatasetBody {
  name: string;
  dataset_type: string;
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

export interface CreateJobBody {
  dataset_id: string;
  preset_id: string;
  created_by?: string;
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
  id: string;
  status: string;
  summary: Record<string, unknown>;
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

export function syncAnnotationsToLs(datasetId: string) {
  return req<SyncResult>(`/datasets/${datasetId}/sync-annotations-to-ls`, {
    method: "POST",
  });
}

export function bulkCreateAnnotations(
  datasetId: string,
  body: BulkAnnotationRequest
) {
  return req<BulkAnnotationResponse>(
    `/datasets/${datasetId}/annotations/bulk`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }
  );
}

export async function listSamplesWithLabels(
  datasetId: string,
  offset = 0,
  limit = 50,
  label?: string,
  orderBy = 'id',
): Promise<PaginatedResponse<SampleWithLabels>> {
  const params = new URLSearchParams()
  params.set('offset', String(offset))
  params.set('limit', String(limit))
  if (label != null) params.set('label', label)
  params.set('order_by', orderBy)
  return req<PaginatedResponse<SampleWithLabels>>(
    `/datasets/${datasetId}/samples-with-labels?${params.toString()}`
  )
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
        dataset_type: body.dataset_type,
        task_spec: body.task_spec ?? { task_type: "classification", label_space: [] },
      }),
    }),

  deleteDataset: (id: string) => req<void>(`/datasets/${id}`, { method: "DELETE" }),

  getDataset: (id: string) => req<Dataset>(`/datasets/${id}`),

  updateLabelSpace: (datasetId: string, labelSpace: string[]) =>
    req<Dataset>(`/datasets/${datasetId}/label-space`, {
      method: "PATCH",
      body: JSON.stringify({ label_space: labelSpace }),
    }),

  getAnnotationStats: (datasetId: string) =>
    req<DatasetAnnotationStats>(`/datasets/${datasetId}/annotation-stats`),

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

  importSamples: (datasetId: string, items: BulkCreateSampleItem[]) =>
    req<BulkCreateSampleResponse>(`/datasets/${datasetId}/samples/import`, {
      method: "POST",
      body: JSON.stringify({ items }),
    }, 120_000),

  getSample: (sampleId: string) => req<Sample>(`/samples/${sampleId}`),

  // ---- Annotations ----
  createAnnotation: (body: CreateAnnotationBody) =>
    req<Annotation>("/annotations", {
      method: "POST",
      body: JSON.stringify({
        sample_id: body.sample_id,
        label: body.label,
        ...(body.created_by !== undefined ? { created_by: body.created_by } : {}),
      }),
    }),

  // ---- Training Presets (read-only catalog) ----
  listPresets: () => req<TrainingPreset[]>("/training-presets"),

  getPreset: (id: string) => req<TrainingPreset>(`/training-presets/${id}`),

  listModelUploadTemplates: () => req<ModelUploadTemplate[]>("/model-upload-templates"),

  // ---- Training Jobs ----
  listJobs: () => req<TrainingJob[]>("/training-jobs"),

  createJob: (dataset_id: string, preset_id: string) =>
    req<TrainingJob>("/training-jobs", {
      method: "POST",
      body: JSON.stringify({ dataset_id, preset_id }),
    }),

  getJob: (id: string) => req<TrainingJob>(`/training-jobs/${id}`),

  cancelJob: (id: string) =>
    req<CancelJobResponse>(`/training-jobs/${id}/cancel`, { method: "POST" }),

  markJobLeft: (id: string) =>
    req<MarkLeftResponse>(`/training-jobs/${id}/mark-left`, { method: "POST" }),

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

  // ---- Models ----
  listModels: (datasetId?: string, jobId?: string) => {
    const params = new URLSearchParams();
    if (datasetId) params.set("dataset_id", datasetId);
    if (jobId) params.set("job_id", jobId);
    const qs = params.toString() ? `?${params.toString()}` : "";
    return req<Model[]>(`/models${qs}`);
  },

  getModel: (id: string) => req<Model>(`/models/${id}`),

  deleteModel: (id: string) => req<void>(`/models/${id}`, { method: "DELETE" }),

  downloadModelUrl: (id: string) => `${API_BASE}/models/${id}/download`,

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

  // ---- Schedules ----
  listSchedules: () => req<Schedule[]>('/schedules'),

  createSchedule: (body: CreateScheduleBody) =>
    req<Schedule>('/schedules', {
      method: 'POST',
      body: JSON.stringify({
        name: body.name,
        flow_name: body.flow_name,
        cron: body.cron,
        parameters: body.parameters ?? {},
        description: body.description ?? '',
      }),
    }),

  getSchedule: (id: string) => req<Schedule>(`/schedules/${id}`),

  updateSchedule: (id: string, body: UpdateScheduleBody) =>
    req<Schedule>(`/schedules/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  deleteSchedule: (id: string) =>
    req<void>(`/schedules/${id}`, { method: 'DELETE' }),

  triggerScheduleRun: (id: string) =>
    req<ScheduleRun>(`/schedules/${id}/run`, { method: 'POST' }),

  pauseSchedule: (id: string) =>
    req<Schedule>(`/schedules/${id}/pause`, { method: 'POST' }),

  resumeSchedule: (id: string) =>
    req<Schedule>(`/schedules/${id}/resume`, { method: 'POST' }),

  listScheduleRuns: (id: string, limit?: number) => {
    const qs = limit !== undefined ? `?limit=${limit}` : '';
    return req<ScheduleRun[]>(`/schedules/${id}/runs${qs}`);
  },

  getRun: (runId: string) => req<ScheduleRun>(`/runs/${runId}`),

  getRunLogs: (runId: string, limit?: number) => {
    const qs = limit !== undefined ? `?limit=${limit}` : '';
    return req<RunLog[]>(`/runs/${runId}/logs${qs}`);
  },

  // ---- Dashboard ----
  getDashboard: () => req<DashboardResponse>('/dashboard'),

  // ---- Task Tracker ----
  listTrackedTasks: (kind?: 'training' | 'prediction') => {
    const qs = kind ? `?kind=${encodeURIComponent(kind)}` : '';
    return req<TaskTrackerSummary[]>(`/task-tracker/tasks${qs}`);
  },

  getTrackedTask: (id: string) => req<TaskTrackerDetail>(`/task-tracker/tasks/${id}`),

  cancelTrackedTask: (id: string) => req<{ cancelled: boolean }>(`/task-tracker/tasks/${id}/cancel`, {
    method: 'POST',
  }),

  // ---- Predictions ----
  runPredictions: (request: RunPredictionRequest) =>
    req<PredictionJob>('/predictions/run', {
      method: 'POST',
      body: JSON.stringify(request),
    }),

  listPredictionJobs: () => req<PredictionJob[]>('/prediction-jobs'),

  getPredictionJob: (id: string) => req<PredictionJob>(`/prediction-jobs/${id}`),

  listPredictionJobPredictions: (id: string) => req<PredictionResult[]>(`/prediction-jobs/${id}/predictions`),

  listPredictionJobEvents: (id: string) => req<PredictionEvent[]>(`/prediction-jobs/${id}/events`),

  cancelPredictionJob: (id: string) => req<{ cancelled: boolean }>(`/prediction-jobs/${id}/cancel`, {
    method: 'POST',
  }),

  predictSingle: (request: PredictSingleRequest) =>
    req<PredictionResult>('/predictions/single', {
      method: 'POST',
      body: JSON.stringify(request),
    }),

  listSamplePredictions: (sampleId: string, modelVersion?: string | null) => {
    const qs = modelVersion ? `?model_version=${encodeURIComponent(modelVersion)}` : '';
    return req<PredictionResult[]>(`/samples/${sampleId}/predictions${qs}`);
  },

  createPredictionCollection: (request: CreatePredictionCollectionRequest) =>
    req<PredictionCollection>('/prediction-collections', {
      method: 'POST',
      body: JSON.stringify(request),
    }),

  listPredictionCollections: (datasetId: string) =>
    req<PredictionCollection[]>(`/prediction-collections?dataset_id=${encodeURIComponent(datasetId)}`),

  syncPredictionCollection: (collectionId: string, syncTag?: string | null) =>
    req<SyncPredictionCollectionResponse>(`/prediction-collections/${collectionId}/sync-label-studio`, {
      method: 'POST',
      body: JSON.stringify(syncTag ? { sync_tag: syncTag } : {}),
    }),

  // ---- Prediction Reviews ----
  createReviewAction: (
    datasetId: string,
    modelId: string,
    modelVersion?: string | null,
    collectionId?: string | null,
    syncTag?: string | null,
  ) =>
    req<ReviewAction>('/prediction-reviews', {
      method: 'POST',
      body: JSON.stringify({
        dataset_id: datasetId,
        model_id: modelId,
        ...(modelVersion ? { model_version: modelVersion } : {}),
        ...(collectionId ? { collection_id: collectionId } : {}),
        ...(syncTag ? { sync_tag: syncTag } : {}),
      }),
    }),

  listReviewActions: (datasetId: string) =>
    req<ReviewAction[]>(`/prediction-reviews?dataset_id=${encodeURIComponent(datasetId)}`),

  getReviewAction: (actionId: string) =>
    req<ReviewAction>(`/prediction-reviews/${actionId}`),

  deleteReviewAction: (actionId: string) =>
    req<void>(`/prediction-reviews/${actionId}`, { method: 'DELETE' }),

  saveReviewAnnotations: (actionId: string, items: SaveReviewAnnotationItem[]) =>
    req<SaveReviewAnnotationsResponse>(
      `/prediction-reviews/${actionId}/annotations`,
      {
        method: 'POST',
        body: JSON.stringify({ items }),
      },
    ),

  listAnnotationVersions: (actionId: string) =>
    req<AnnotationVersion[]>(`/prediction-reviews/${actionId}/annotation-versions`),

  listExportFormats: () =>
    req<ExportFormat[]>('/export-formats'),

  previewReviewExport: (actionId: string, formatId?: string) => {
    const params = new URLSearchParams();
    if (formatId) params.set('format_id', formatId);
    const qs = params.toString() ? `?${params.toString()}` : '';
    return req<Record<string, unknown>>(`/prediction-reviews/${actionId}/export${qs}`);
  },

  persistReviewExport: (actionId: string, formatId?: string) =>
    req<VersionExportResponse>(
      `/prediction-reviews/${actionId}/export/persist`,
      {
        method: 'POST',
        body: JSON.stringify({
          format_id: formatId ?? 'annotation-version-full-context-v1',
        }),
      },
    ),

  // ---- Public visibility toggles (superadmin) ----
  toggleDatasetPublic: (id: string, isPublic: boolean) =>
    req<Dataset>(`/datasets/${id}/public`, {
      method: "PATCH",
      body: JSON.stringify({ is_public: isPublic }),
    }),

  toggleJobPublic: (id: string, isPublic: boolean) =>
    req<TrainingJob>(`/training-jobs/${id}/public`, {
      method: "PATCH",
      body: JSON.stringify({ is_public: isPublic }),
    }),
};

// ---------------------------------------------------------------------------
// Organizations
// ---------------------------------------------------------------------------

export async function fetchOrganizations(): Promise<Organization[]> {
  return req<Organization[]>('/organizations');
}

// ---------------------------------------------------------------------------
// Auth functions
// ---------------------------------------------------------------------------

export async function authLogin(email: string, password: string): Promise<LoginResponse> {
  const r = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) {
    let detail = `login failed: ${r.status}`;
    try {
      const body = await r.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
    } catch { /* ignore */ }
    throw new ApiError(detail, r.status);
  }
  return r.json() as Promise<LoginResponse>;
}

export async function authRegister(name: string, email: string, password: string): Promise<User> {
  const r = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password }),
  });
  if (!r.ok) {
    let detail = `register failed: ${r.status}`;
    try {
      const body = await r.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
    } catch { /* ignore */ }
    throw new ApiError(detail, r.status);
  }
  return r.json() as Promise<User>;
}

export async function authMe(token: string): Promise<UserWithOrgs> {
  const r = await fetch(`${API_BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) {
    let detail = `auth/me failed: ${r.status}`;
    try {
      const body = await r.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
    } catch { /* ignore */ }
    throw new ApiError(detail, r.status);
  }
  return r.json() as Promise<UserWithOrgs>;
}

// ---------------------------------------------------------------------------
// SSE helper
// ---------------------------------------------------------------------------

export function buildJobEventSource(jobId: string): EventSource {
  let tokenParam = "";
  try {
    const authStore = useAuthStore();
    const token = authStore.token ?? getStoredToken();
    if (token) {
      tokenParam = `?token=${encodeURIComponent(token)}`;
    }
  } catch {
    /* ignore */
  }
  return new EventSource(`${API_BASE}/training-jobs/${jobId}/events${tokenParam}`);
}

export function buildTrackedTaskEventSource(taskId: string): EventSource {
  let tokenParam = "";
  try {
    const authStore = useAuthStore();
    const token = authStore.token ?? getStoredToken();
    if (token) {
      tokenParam = `?token=${encodeURIComponent(token)}`;
    }
  } catch {
    /* ignore */
  }
  return new EventSource(`${API_BASE}/task-tracker/tasks/${taskId}/stream${tokenParam}`);
}

// ---------------------------------------------------------------------------
// Agent / Display Surface API
// ---------------------------------------------------------------------------

export async function getSurfaceState(
  sessionId: string,
  surfaceId: string
): Promise<import("./types").SurfaceStateDocument> {
  return req(`/sessions/${sessionId}/surfaces/${surfaceId}`);
}

export async function setSurfacePanel(
  sessionId: string,
  surfaceId: string,
  panel: import("./types").AgentPanelDescriptor
): Promise<import("./types").SurfaceStateDocument> {
  return req(`/sessions/${sessionId}/surfaces/${surfaceId}/panels`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ panel }),
  });
}

export async function removeSurfacePanel(
  sessionId: string,
  surfaceId: string,
  panelId: string
): Promise<import("./types").SurfaceStateDocument> {
  return req(`/sessions/${sessionId}/surfaces/${surfaceId}/panels/${panelId}`, {
    method: "DELETE",
  });
}

export async function exportSurfaceState(
  sessionId: string,
  surfaceId: string
): Promise<import("./types").SurfaceStateDocument> {
  return req(`/sessions/${sessionId}/surfaces/${surfaceId}/export`);
}

export async function importSurfaceState(
  sessionId: string,
  surfaceId: string,
  doc: import("./types").SurfaceStateDocument
): Promise<import("./types").SurfaceStateDocument> {
  return req(`/sessions/${sessionId}/surfaces/${surfaceId}/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(doc),
  });
}

export async function queryDatasetData(
  datasetId: string,
  queryType: string,
  params: Record<string, unknown> = {}
): Promise<Record<string, unknown>> {
  return req(`/datasets/${datasetId}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query_type: queryType, params }),
  });
}

/**
 * Send a chat message to the agent and return an EventSource for SSE streaming.
 * The caller must close the EventSource when done.
 */
export function sendAgentChat(
  datasetId: string,
  message: string
): { eventSource: EventSource; abort: () => void } {
  // Use fetch + ReadableStream for POST-based SSE (EventSource only supports GET).
  // We fake an EventSource-like interface using a custom approach.
  const controller = new AbortController();
  const token = (() => {
    try {
      const authStore = useAuthStore();
      return authStore.token ?? getStoredToken();
    } catch {
      return getStoredToken();
    }
  })();

  const url = `${API_BASE}/datasets/${datasetId}/agent/chat`;

  // We return a minimal object; the composable will use fetch directly
  // because EventSource doesn't support POST.
  return {
    eventSource: null as unknown as EventSource, // not used
    abort: () => controller.abort(),
  };
}

/**
 * POST-based SSE streaming for agent chat.
 * Returns an async generator of parsed SSE events.
 */
export async function* streamAgentChat(
  datasetId: string,
  userMessage: string,
  signal?: AbortSignal
): AsyncGenerator<{ event: string; data: string }> {
  const token = (() => {
    try {
      const authStore = useAuthStore();
      return authStore.token ?? getStoredToken();
    } catch {
      return getStoredToken();
    }
  })();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const resp = await fetch(`${API_BASE}/datasets/${datasetId}/agent/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message: userMessage }),
    signal,
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new ApiError(text || resp.statusText, resp.status);
  }

  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Parse SSE frames from buffer
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    let currentEvent = "message";
    let currentData = "";

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        currentData = line.slice(6);
      } else if (line === "") {
        // End of SSE frame
        if (currentData) {
          yield { event: currentEvent, data: currentData };
        }
        currentEvent = "message";
        currentData = "";
      }
    }
  }
}
