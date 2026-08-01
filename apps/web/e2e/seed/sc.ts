/**
 * SC seed helpers — import, annotate, sample listing for live-mode tests.
 *
 * IMPORTANT: call {@link getSeedClient} (from `./client`) with a valid
 * token BEFORE calling any of these functions.
 */
import type {
  ScImportRequest,
  ScImportResponse,
  ScBulkAnnotationRequest,
  ScAnnotationItem,
  ScInspectionSummaryItem,
  Dataset,
} from "../../src/generated/orval/models";
import { tableFromIPC, type Table } from "apache-arrow";
import {
  getInspectionsApiV1ScInspectionsGet,
  startScImportApiV1ScImportPost,
  scBulkCreateAnnotationsApiV1DatasetsDatasetIdAnnotationsBulkScPost,
  listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet,
  listDatasetsApiV1DatasetsGet,
} from "../../src/generated/orval/endpoints/api";
import { requestRaw } from "../../src/shared/api/client";
import { E2E_TIMEOUTS } from "../timeouts";

const SC_DATA_PROVIDER_BASE = process.env["SC_DATA_PROVIDER_URL"] ?? "http://localhost:8001/api/v1";

async function queryScDataset(
  datasetId: string,
  description: string,
  sql: string,
  parameters: Array<boolean | number | string | boolean[] | number[] | string[] | null>,
): Promise<Table> {
  const response = await requestRaw(
    `${SC_DATA_PROVIDER_BASE}/sc/data/datasets/${datasetId}/query`,
    {
      method: "POST",
      body: JSON.stringify({ description, sql, parameters }),
    },
    E2E_TIMEOUTS.operation.scDataLoad,
  );
  return tableFromIPC(new Uint8Array(await response.arrayBuffer()));
}

/** Verify completed predictions through the SQL/Arrow workbench read path. */
export async function countScPredictionsForTestIds(
  datasetId: string,
  testIds: number[],
): Promise<number> {
  const table = await queryScDataset(
    datasetId,
    "e2e.sc.prediction-count",
    "SELECT count(*) AS predicted FROM samples WHERE test_id = ANY(?) AND prediction_label IS NOT NULL",
    [testIds],
  );
  return Number(table.getChild("predicted")?.get(0) ?? 0);
}

/**
 * Start an SC dataset import via the API.
 *
 * Returns the import response which includes `flow_run_id` and status.
 * The import runs asynchronously; use {@link waitForScImportByDatasetName}
 * to wait for the dataset to appear and get its ID.
 */
export async function startScImport(req: ScImportRequest): Promise<ScImportResponse> {
  return startScImportApiV1ScImportPost(req);
}

/** Resolve an inspection that the current SC upstream can actually serve. */
export async function getLatestScInspection(): Promise<ScInspectionSummaryItem> {
  const response = await getInspectionsApiV1ScInspectionsGet({
    start_time: new Date(Date.now() - 48 * 3600_000).toISOString(),
    end_time: new Date(Date.now() + 3600_000).toISOString(),
  });
  const inspection = response.items[0];
  if (!inspection) {
    throw new Error("SC upstream returned no inspections in the last 48 hours");
  }
  return inspection;
}

/**
 * Poll the dataset list until a dataset with the given name appears,
 * returning its ID. Throws after `timeoutMs`.
 */
export async function waitForScImportByDatasetName(
  datasetName: string,
  timeoutMs = E2E_TIMEOUTS.operation.scImport,
): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const page = await listDatasetsApiV1DatasetsGet();
    const datasets: Dataset[] = page.items;
    const found = datasets.find((d) => d.name === datasetName);
    if (found?.id) return found.id;
    await new Promise((resolve) => setTimeout(resolve, E2E_TIMEOUTS.pollInterval));
  }
  throw new Error(`SC import for "${datasetName}" did not complete within ${timeoutMs}ms`);
}

/**
 * Bulk-create annotations for SC dataset samples.
 */
export async function scBulkAnnotate(
  datasetId: string,
  annotations: ScAnnotationItem[],
): Promise<{ created: number }> {
  const req: ScBulkAnnotationRequest = { annotations };
  return scBulkCreateAnnotationsApiV1DatasetsDatasetIdAnnotationsBulkScPost(datasetId, req);
}

/** Shape of a single sample item from the patch_image_v1 view. */
export interface ScSampleItem {
  defect_id: string;
  sample_id: string;
}

interface ScSampleListBody {
  items?: ScSampleItem[];
  total?: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isScSampleItem(value: unknown): value is ScSampleItem {
  return (
    isRecord(value) && typeof value.defect_id === "string" && typeof value.sample_id === "string"
  );
}

function parseScSampleListBody(value: unknown): ScSampleListBody {
  if (!isRecord(value)) throw new Error("SC sample response must be an object");
  const items = Array.isArray(value.items) ? value.items.filter(isScSampleItem) : [];
  const total = typeof value.total === "number" ? value.total : items.length;
  return { items, total };
}

/**
 * List all samples from an SC dataset via the patch_image_v1 view.
 *
 * Paginates automatically through all items.
 */
export async function listScSamples(
  datasetId: string,
  maxItems: number | null = null,
): Promise<ScSampleItem[]> {
  const allItems: ScSampleItem[] = [];
  let offset = 0;
  const limit = 200;

  while (true) {
    const body = parseScSampleListBody(
      await listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet(
        datasetId,
        "patch_image_v1",
        { offset, limit },
      ),
    );
    const items = body.items ?? [];
    if (items.length === 0) break;
    const remaining = maxItems === null ? items.length : Math.max(0, maxItems - allItems.length);
    allItems.push(...items.slice(0, remaining));
    if (maxItems !== null && allItems.length >= maxItems) break;
    offset += limit;
    if (offset >= (body.total ?? 0)) break;
  }

  return allItems;
}

/**
 * Import an SC dataset and annotate it with deterministic labels — combined helper
 * for Phase 3 and Phase 4 seed setup.
 *
 * @param inspectionTime  ISO inspection time string
 * @param waferKey        Wafer key number
 * @param annotateCount   Number of samples to annotate
 * @param labels          Label space assigned round-robin
 * @returns The dataset ID and count of annotated samples
 */
export async function setupScImportedAndAnnotated(
  inspectionTime: string,
  waferKey: number,
  annotateCount: number,
  labels: string[],
  datasetName = `wafer-seed-${Date.now()}`,
): Promise<{ datasetId: string; annotated: number; workflowTestIds: number[] }> {
  const importReq: ScImportRequest = {
    source_inspection_time: inspectionTime,
    source_wafer_key: waferKey,
    dataset_name: datasetName,
    storage_mode: "file_shard_sparse",
  };

  await startScImport(importReq);
  const datasetId = await waitForScImportByDatasetName(datasetName);

  // Training setup needs only the annotated subset. Fetching every row from a
  // 300k sparse dataset turns a 100-sample fixture into 1,500 HTTP requests.
  const samples = await listScSamples(datasetId, annotateCount);
  const toAnnotate = Math.min(annotateCount, samples.length);
  if (labels.length === 0) throw new Error("SC annotation seed requires at least one label");
  const annotations: ScAnnotationItem[] = samples.slice(0, toAnnotate).map((item, index) => ({
    defect_id: item.defect_id,
    label: labels[index % labels.length],
  }));

  const result = await scBulkAnnotate(datasetId, annotations);

  // The generic patch-image projection intentionally omits workbench-only
  // columns such as test_id. Resolve those columns through the same SQL/Arrow
  // data-source interface used by the page so this fixture also exercises the
  // DuckDB provider contract.
  const table = await queryScDataset(
    datasetId,
    "e2e.sc.training-sample-ids",
    "SELECT defect_id, test_id FROM samples WHERE defect_id = ANY(?) ORDER BY defect_id LIMIT ?",
    [samples.slice(0, toAnnotate).map((sample) => Number(sample.defect_id)), toAnnotate],
  );
  const defectIds = table.getChild("defect_id");
  const testIds = table.getChild("test_id");
  const testIdByDefectId = new Map<string, number>();
  for (let index = 0; index < table.numRows; index += 1) {
    testIdByDefectId.set(String(defectIds?.get(index)), Number(testIds?.get(index)));
  }
  const workflowTestIds = new Set<number>();
  const coveredLabels = new Set<string>();
  for (let index = 0; index < samples.length; index += 1) {
    const sample = samples[index];
    if (!sample) continue;
    const testId = testIdByDefectId.get(sample.defect_id);
    const label = labels[index % labels.length];
    if (typeof testId !== "number" || testId < 1 || testId > 500 || !label) continue;
    if (coveredLabels.has(label)) continue;
    workflowTestIds.add(testId);
    coveredLabels.add(label);
    if (coveredLabels.size === labels.length) break;
  }
  if (coveredLabels.size < 2) {
    throw new Error("SC workbench query did not return Test IDs covering two annotated labels");
  }
  return {
    datasetId,
    annotated: result.created ?? annotations.length,
    workflowTestIds: Array.from(workflowTestIds),
  };
}
