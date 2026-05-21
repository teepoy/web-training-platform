import { req } from "@/shared/api";
import type {
  Schedule,
  ScheduleRun,
  RunLog,
  CreateScheduleBody,
  UpdateScheduleBody,
} from '../domain/models';

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

export function getRun(runId: string): Promise<ScheduleRun> {
  return req<ScheduleRun>(`/runs/${runId}`);
}

export function getRunLogs(runId: string, limit?: number): Promise<RunLog[]> {
  const qs = limit !== undefined ? `?limit=${limit}` : "";
  return req<RunLog[]>(`/runs/${runId}/logs${qs}`);
}

export type { UpdateScheduleBody } from '../domain/models';
