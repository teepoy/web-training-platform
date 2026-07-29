import type { Page } from "@playwright/test";
import type {
  PredictionJobResponse,
  PredictionResultResponse,
  ModelResponse,
} from "@/generated/orval/models";
import { makePredictionJob, makePredictionResult, makeModel } from "../factories";

export async function mockListPredictionJobs(
  page: Page,
  jobs?: PredictionJobResponse[],
): Promise<void> {
  const body = jobs ?? [];
  await page.route("**/api/v1/prediction-jobs**", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    const url = new URL(route.request().url());
    const datasetId = url.searchParams.get("dataset_id");
    const filteredBody = datasetId ? body.filter((job) => job.dataset_id === datasetId) : body;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: filteredBody, total: filteredBody.length }),
    });
  });
}

export async function mockGetPredictionJob(
  page: Page,
  jobId: string,
  job?: Partial<PredictionJobResponse>,
): Promise<void> {
  const body = makePredictionJob({ id: jobId, status: "completed", ...job });
  await page.route(`**/api/v1/prediction-jobs/${jobId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

export async function mockRunPrediction(
  page: Page,
  datasetId: string,
  modelId: string,
  jobId = "prediction-job-1",
): Promise<void> {
  await page.route("**/api/v1/predictions/run", async (route) => {
    const body = makePredictionJob({
      id: jobId,
      dataset_id: datasetId,
      model_id: modelId,
      status: "queued",
    });
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

export async function mockListModels(page: Page, models?: ModelResponse[]): Promise<void> {
  const body = models ?? [makeModel()];
  await page.route("**/api/v1/models", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

export async function mockTaskTracker(page: Page, taskId: string): Promise<void> {
  await page.route(`**/api/v1/task-tracker/tasks/${taskId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: taskId,
        task_kind: "prediction",
        meta: {},
        raw: {
          platform_job: {},
          flow_run: null,
          deployment: null,
          work_queue: null,
          work_pool: null,
          logs: [],
        },
        derived: {
          task_kind: "prediction",
          execution_kind: "prefect",
          display_status: "running",
          prefect_state: null,
          stage: "running",
          active_node: null,
          capacity_status: "unknown",
          queue_priority: null,
          queue_priority_label: "none",
          queue_depth_ahead: null,
          pool_concurrency_limit: null,
          pool_slots_used: null,
          stages: [],
          scorecard: { errors: 0, warnings: 0, checks: [] },
          summary_metrics: {},
          artifacts: [],
          dynamic_console_lines: [],
          deep_links: {},
        },
      }),
    });
  });
}
