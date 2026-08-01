/**
 * Prediction seed helpers — run predictions and fetch results.
 */
import type {
  ModelResponse,
  RunPredictionRequest,
  PredictionJobResponse,
  PredictionResultResponse,
} from "../../src/generated/orval/models";
import {
  getPredictionJobApiV1PredictionJobsJobIdGet,
  listModelsApiV1ModelsGet,
  runPredictionsApiV1PredictionsRunPost,
  listPredictionJobPredictionsApiV1PredictionJobsJobIdPredictionsGet,
  listPredictionJobsApiV1PredictionJobsGet,
} from "../../src/generated/orval/endpoints/api";
import { E2E_TIMEOUTS } from "../timeouts";

/**
 * Submit a batch prediction job.
 *
 * IMPORTANT: call {@link getSeedClient} (from `./client`) with a valid
 * token BEFORE calling this.
 */
export async function runPrediction(req: RunPredictionRequest): Promise<PredictionJobResponse> {
  return runPredictionsApiV1PredictionsRunPost(req);
}

/**
 * Get the prediction results for a completed prediction job.
 *
 * Returns all results (the backend does not paginate this endpoint).
 */
export async function getPredictionResults(jobId: string): Promise<PredictionResultResponse[]> {
  return listPredictionJobPredictionsApiV1PredictionJobsJobIdPredictionsGet(jobId);
}

export async function findFirstModelForDataset(datasetId: string): Promise<string> {
  const response = await listModelsApiV1ModelsGet({ dataset_id: datasetId });
  const models: ModelResponse[] = response.items;
  const modelId = models[0]?.id;
  if (!modelId) throw new Error(`No models found for dataset ${datasetId}`);
  return modelId;
}

export async function waitForPredictionCompletion(
  jobId: string,
  options?: { interval?: number; timeout?: number },
): Promise<PredictionJobResponse> {
  const interval = options?.interval ?? E2E_TIMEOUTS.pollInterval;
  const timeout = options?.timeout ?? E2E_TIMEOUTS.operation.prediction;
  const deadline = Date.now() + timeout;

  while (Date.now() < deadline) {
    const job = await getPredictionJobApiV1PredictionJobsJobIdGet(jobId);
    const status = String(job.status ?? "").toLowerCase();
    if (status === "completed") return job;
    if (status === "failed" || status === "cancelled") {
      throw new Error(`Prediction job ${jobId} reached terminal state "${status}"`);
    }
    await new Promise((resolve) => setTimeout(resolve, interval));
  }

  throw new Error(`Prediction job ${jobId} did not complete within ${timeout}ms`);
}

/** Wait for the prediction created by the combined SC train-and-predict workflow. */
export async function waitForWorkflowPredictionCompletion(
  datasetId: string,
  trainingJobId: string,
  options?: { interval?: number; timeout?: number },
): Promise<PredictionJobResponse> {
  const interval = options?.interval ?? E2E_TIMEOUTS.pollInterval;
  const timeout = options?.timeout ?? E2E_TIMEOUTS.operation.prediction;
  const deadline = Date.now() + timeout;

  while (Date.now() < deadline) {
    const response = await listPredictionJobsApiV1PredictionJobsGet({
      dataset_id: datasetId,
      limit: 200,
    });
    const job = response.items.find(
      (candidate) => candidate.summary?.source_training_job_id === trainingJobId,
    );
    if (job) {
      const status = String(job.status ?? "").toLowerCase();
      if (status === "completed") return job;
      if (status === "failed" || status === "cancelled") {
        throw new Error(`Workflow prediction job ${job.id} reached terminal state "${status}"`);
      }
    }
    await new Promise((resolve) => setTimeout(resolve, interval));
  }

  throw new Error(
    `Workflow prediction for training job ${trainingJobId} did not complete within ${timeout}ms`,
  );
}
