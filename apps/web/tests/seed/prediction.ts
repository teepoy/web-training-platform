/**
 * Prediction seed helpers — run predictions and fetch results.
 */
import type {
  RunPredictionRequest,
  PredictionJobResponse,
  PredictionResultResponse,
} from '../../src/generated/orval/models';
import {
  runPredictionsApiV1PredictionsRunPost,
  listPredictionJobPredictionsApiV1PredictionJobsJobIdPredictionsGet,
} from '../../src/generated/orval/endpoints/api';

/**
 * Submit a batch prediction job.
 *
 * IMPORTANT: call {@link getSeedClient} (from `./client`) with a valid
 * token BEFORE calling this.
 */
export async function runPrediction(
  req: RunPredictionRequest,
): Promise<PredictionJobResponse> {
  const res = await runPredictionsApiV1PredictionsRunPost(req);
  return res.data as PredictionJobResponse;
}

/**
 * Get the prediction results for a completed prediction job.
 *
 * Returns all results (the backend does not paginate this endpoint).
 */
export async function getPredictionResults(
  jobId: string,
): Promise<PredictionResultResponse[]> {
  const res = await listPredictionJobPredictionsApiV1PredictionJobsJobIdPredictionsGet(jobId);
  return res.data as PredictionResultResponse[];
}
