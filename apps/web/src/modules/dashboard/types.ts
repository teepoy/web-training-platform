export interface WorkPoolStatus {
  name: string;
  type: string;
  is_paused: boolean;
  concurrency_limit: number | null;
  slots_used: number;
  status: string;
}

export interface JobQueueStats {
  queued: number;
  running: number;
  completed: number;
  failed: number;
  cancelled: number;
}

export interface RecentJobSummary {
  id: string;
  dataset_id: string;
  preset_id: string;
  status: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface ServiceStatus {
  name: string;
  kind: string;
  status: string;
  detail: string;
  latency_ms: number | null;
  endpoint: string | null;
}

export interface DashboardResponse {
  work_pool: WorkPoolStatus | null;
  job_queue: JobQueueStats;
  recent_jobs: RecentJobSummary[];
  services: ServiceStatus[];
  prefect_connected: boolean;
}
