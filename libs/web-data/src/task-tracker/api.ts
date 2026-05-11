import { req } from "../client/apiClient";

export interface TaskTrackerSummary {
  id: string;
  task_kind: string;
  execution_kind: string;
  display_name: string;
  display_status: string;
  stage: string;
  dataset_id: string;
  model_id: string | null;
  preset_id: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  prefect_state: string | null;
  work_pool_name: string | null;
  work_queue_name: string | null;
  queue_priority: number | null;
  queue_priority_label: string;
  queue_depth_ahead: number | null;
  capacity_status: string;
  pool_concurrency_limit: number | null;
  pool_slots_used: number | null;
}

export interface TaskTrackerDetail {
  id: string;
  task_kind: string;
  meta: Record<string, unknown>;
  raw: {
    platform_job: Record<string, unknown>;
    flow_run: Record<string, unknown> | null;
    deployment: Record<string, unknown> | null;
    work_queue: Record<string, unknown> | null;
    work_pool: Record<string, unknown> | null;
    logs: Record<string, unknown>[];
  };
  derived: {
    task_kind: string;
    execution_kind: string;
    display_status: string;
    prefect_state: string | null;
    stage: string;
    active_node: string | null;
    capacity_status: string;
    queue_priority: number | null;
    queue_priority_label: string;
    queue_depth_ahead: number | null;
    pool_concurrency_limit: number | null;
    pool_slots_used: number | null;
    stages: Array<{
      key: string;
      label: string;
      status: string;
      summary: string;
      nodes: Array<{
        key: string;
        label: string;
        status: string;
        detail: string;
        expected_start_at: string | null;
        started_at: string | null;
        ended_at: string | null;
      }>;
    }>;
    scorecard: {
      errors: number;
      warnings: number;
      checks: Array<{
        key: string;
        label: string;
        status: string;
        message: string;
        value: string | null;
      }>;
    };
    summary_metrics: {
      total: number | null;
      processed: number | null;
      successful: number | null;
      failed: number | null;
      skipped: number | null;
      rate_hint: string | null;
    };
    artifacts: Record<string, unknown>[];
    dynamic_console_lines: string[];
    deep_links: {
      prefect_run_url: string | null;
      prefect_deployment_url: string | null;
      platform_job_url: string | null;
    };
  };
}

export function listTrackedTasks(kind?: "training" | "prediction"): Promise<TaskTrackerSummary[]> {
  const qs = kind ? `?kind=${encodeURIComponent(kind)}` : "";
  return req<TaskTrackerSummary[]>(`/task-tracker/tasks${qs}`);
}

export function getTrackedTask(id: string): Promise<TaskTrackerDetail> {
  return req<TaskTrackerDetail>(`/task-tracker/tasks/${id}`);
}

export function cancelTrackedTask(id: string): Promise<{ cancelled: boolean }> {
  return req<{ cancelled: boolean }>(`/task-tracker/tasks/${id}/cancel`, {
    method: "POST",
  });
}
