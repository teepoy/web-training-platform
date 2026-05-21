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

export interface RunLog {
  id: string | null;
  flow_run_id: string | null;
  level: number;
  timestamp: string;
  message: string;
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

export type ScheduleStatus = "active" | "paused";
