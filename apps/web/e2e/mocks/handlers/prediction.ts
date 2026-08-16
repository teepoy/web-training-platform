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
  await page.route("**/api/v1/models**", async (route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === "DELETE") {
      const modelId = url.pathname.split("/").pop();
      const index = body.findIndex((model) => model.id === modelId);
      if (index >= 0) body.splice(index, 1);
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    if (url.pathname.endsWith("/models/creators")) {
      const creators = new Map<string, string>();
      for (const model of body) {
        if (model.created_by) {
          creators.set(model.created_by, model.creator_name || model.created_by);
        }
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([...creators].map(([id, name]) => ({ id, name }))),
      });
      return;
    }
    const query = url.searchParams.get("q")?.trim().toLocaleLowerCase();
    const creatorId = url.searchParams.get("creator_id");
    const sourceType = url.searchParams.get("source_type");
    const sortBy = url.searchParams.get("sort_by") ?? "created_at";
    const sortOrder = url.searchParams.get("sort_order") ?? "desc";
    const filtered = body.filter((model) => {
      if (creatorId && model.created_by !== creatorId) return false;
      if (sourceType === "dataset" && !model.dataset_id) return false;
      if (sourceType === "collection" && !model.collection_id) return false;
      if (!query) return true;
      return [
        model.id,
        model.name,
        model.format,
        model.job_id,
        model.dataset_id,
        model.dataset_name,
        model.trainer_name,
        model.created_by,
        model.creator_name,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLocaleLowerCase().includes(query));
    });
    filtered.sort((left, right) => {
      const leftValue =
        sortBy === "name"
          ? left.name
          : sortBy === "creator"
            ? left.creator_name
            : sortBy === "source"
              ? left.dataset_name || left.collection_name
              : sortBy === "trainer"
                ? left.trainer_name
                : left.created_at;
      const rightValue =
        sortBy === "name"
          ? right.name
          : sortBy === "creator"
            ? right.creator_name
            : sortBy === "source"
              ? right.dataset_name || right.collection_name
              : sortBy === "trainer"
                ? right.trainer_name
                : right.created_at;
      const result = String(leftValue ?? "").localeCompare(String(rightValue ?? ""));
      return sortOrder === "asc" ? result : -result;
    });
    const offset = Number(url.searchParams.get("offset") ?? 0);
    const limit = Number(url.searchParams.get("limit") ?? filtered.length);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: filtered.slice(offset, offset + limit),
        total: filtered.length,
      }),
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
