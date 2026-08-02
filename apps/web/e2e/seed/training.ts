/**
 * Training job seed helpers — start jobs and poll for status.
 */
import type { CreateTrainingJobRequest, TrainingJob } from "../../src/generated/orval/models";
import {
  cancelJobApiV1TrainingJobsJobIdCancelPost,
  createTrainingJobApiV1TrainingJobsPost,
  getJobApiV1TrainingJobsJobIdGet,
  listTrainersRouteApiV1TrainersGet,
} from "../../src/generated/orval/endpoints/api";
import { E2E_TIMEOUTS } from "../timeouts";

/**
 * Thrown by {@link waitForJobStatus} when the job does not reach the
 * expected status within the timeout window.
 */
export class JobPollTimeoutError extends Error {
  constructor(jobId: string, expectedStatus: string, timeoutMs: number) {
    super(`Job ${jobId} did not reach status "${expectedStatus}" within ${timeoutMs}ms`);
    this.name = "JobPollTimeoutError";
  }
}

/**
 * List available trainers.
 *
 * IMPORTANT: call {@link getSeedClient} (from `./client`) with a valid
 * token BEFORE calling this.
 */
export async function listTrainers(): Promise<Record<string, unknown>[]> {
  return listTrainersRouteApiV1TrainersGet();
}

/**
 * Start a training job.
 *
 * IMPORTANT: call {@link getSeedClient} (from `./client`) with a valid
 * token BEFORE calling this.
 */
export async function startTrainingJob(req: CreateTrainingJobRequest): Promise<TrainingJob> {
  return createTrainingJobApiV1TrainingJobsPost(req);
}

export async function cancelTrainingJobAndWait(
  jobId: string,
  opts?: { interval?: number; timeout?: number },
): Promise<TrainingJob> {
  const interval = opts?.interval ?? E2E_TIMEOUTS.pollInterval;
  const timeout = opts?.timeout ?? E2E_TIMEOUTS.operation.jobCancellation;
  const deadline = Date.now() + timeout;
  let job = await getJobApiV1TrainingJobsJobIdGet(jobId);

  if (job.status === "completed" || job.status === "failed" || job.status === "cancelled") {
    return job;
  }

  await cancelJobApiV1TrainingJobsJobIdCancelPost(jobId);
  while (Date.now() < deadline) {
    job = await getJobApiV1TrainingJobsJobIdGet(jobId);
    if (job.status === "completed" || job.status === "failed" || job.status === "cancelled") {
      return job;
    }
    await new Promise((resolve) => setTimeout(resolve, interval));
  }

  throw new JobPollTimeoutError(jobId, "terminal state after cancellation", timeout);
}

/**
 * Poll a training job until it reaches the expected status.
 *
 * @param jobId     The training job ID.
 * @param status    Expected final status (e.g. `"completed"`).
 * @param opts      Optional polling configuration.
 * @param opts.interval  Poll interval in ms (defaults to the shared E2E policy).
 * @param opts.timeout   Max wait time in ms (defaults to the shared training budget).
 * @throws JobPollTimeoutError if timeout expires.
 * @throws Error if the job reaches a terminal failure state (`failed` / `cancelled`).
 */
export async function waitForJobStatus(
  jobId: string,
  status: string,
  opts?: { interval?: number; timeout?: number },
): Promise<TrainingJob> {
  const interval = opts?.interval ?? E2E_TIMEOUTS.pollInterval;
  const timeout = opts?.timeout ?? E2E_TIMEOUTS.operation.training;
  const deadline = Date.now() + timeout;

  while (Date.now() < deadline) {
    const job = await getJobApiV1TrainingJobsJobIdGet(jobId);

    if (job.status === status) return job;

    if (job.status === "failed" || job.status === "cancelled") {
      throw new Error(`Job ${jobId} reached terminal state "${job.status}" (expected "${status}")`);
    }

    await new Promise((r) => setTimeout(r, interval));
  }

  throw new JobPollTimeoutError(jobId, status, timeout);
}
