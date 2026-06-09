import { getRunLogsApiV1RunsRunIdLogsGet } from "@/generated/orval/endpoints/api";
import type { RunLogResponse as RunLog } from "@/generated/orval/models";

export async function getRunLogs(runId: string, limit?: number): Promise<RunLog[]> {
  return (await
    getRunLogsApiV1RunsRunIdLogsGet(
      runId,
      limit !== undefined ? { limit } : undefined,
    )).data as RunLog[];
}
