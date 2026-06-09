/**
 * Schedule seed helpers — create, pause, resume, delete schedules.
 */
import type {
  CreateScheduleRequest,
  ScheduleResponse,
} from '../../src/generated/orval/models';
import {
  createScheduleApiV1SchedulesPost,
  pauseScheduleApiV1SchedulesScheduleIdPausePost,
  resumeScheduleApiV1SchedulesScheduleIdResumePost,
  deleteScheduleApiV1SchedulesScheduleIdDelete,
} from '../../src/generated/orval/endpoints/api';

/**
 * Create a new schedule.
 *
 * IMPORTANT: call {@link getSeedClient} (from `./client`) with a valid
 * token BEFORE calling this.
 */
export async function createSchedule(
  req: CreateScheduleRequest,
): Promise<ScheduleResponse> {
  const res = await createScheduleApiV1SchedulesPost(req);
  return res.data as ScheduleResponse;
}

/**
 * Pause an active schedule.
 */
export async function pauseSchedule(scheduleId: string): Promise<ScheduleResponse> {
  const res = await pauseScheduleApiV1SchedulesScheduleIdPausePost(scheduleId);
  return res.data as ScheduleResponse;
}

/**
 * Resume a paused schedule.
 */
export async function resumeSchedule(scheduleId: string): Promise<ScheduleResponse> {
  const res = await resumeScheduleApiV1SchedulesScheduleIdResumePost(scheduleId);
  return res.data as ScheduleResponse;
}

/**
 * Delete a schedule by ID.
 */
export async function deleteSchedule(scheduleId: string): Promise<void> {
  await deleteScheduleApiV1SchedulesScheduleIdDelete(scheduleId);
}
