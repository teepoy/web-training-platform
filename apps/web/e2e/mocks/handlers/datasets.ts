import type { Page } from "@playwright/test";
import type {
  Dataset,
  SampleWithLabels,
  DatasetAnnotationStats,
  DatasetStatusResponse,
  PaginatedResponseSampleWithLabels,
} from "@/generated/orval/models";
import { makeFlowerDataset, makeSample, makeSamples } from "../factories";

export async function mockListDatasets(page: Page, datasets?: Dataset[]): Promise<void> {
  const body = datasets ?? [makeFlowerDataset()];
  await page.route("**/api/v1/datasets**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: body, total: body.length }),
    });
  });
}

export async function mockGetDataset(
  page: Page,
  id: string,
  dataset?: Partial<Dataset>,
): Promise<void> {
  const body: Dataset = {
    id,
    name: "flowers-dataset",
    dataset_type: "image_classification",
    task_spec: { task_type: "classification", label_space: ["rose", "tulip"] },
    created_at: "2026-01-01T00:00:00Z",
    org_id: "org-e2e-1",
    org_name: "E2E Org",
    is_public: false,
    ...dataset,
  };
  await page.route(`**/api/v1/datasets/${id}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

export async function mockListSamples(
  page: Page,
  datasetId: string,
  samples?: SampleWithLabels[],
): Promise<void> {
  const items = samples ?? makeSamples(datasetId, 2);
  const body: PaginatedResponseSampleWithLabels = { items, total: items.length };
  await page.route(`**/api/v1/datasets/${datasetId}/samples-with-labels**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

export async function mockAnnotationStats(
  page: Page,
  datasetId: string,
  stats?: Partial<DatasetAnnotationStats>,
): Promise<void> {
  const total = stats?.total_samples ?? 2;
  const body: DatasetAnnotationStats = {
    total_samples: total,
    annotated_samples: 0,
    unlabeled_samples: total,
    label_counts: {},
    ...stats,
  };
  await page.route(`**/api/v1/datasets/${datasetId}/annotation-stats`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

export async function mockGetSample(
  page: Page,
  datasetId: string,
  sampleId: string,
  sample?: Partial<SampleWithLabels>,
): Promise<void> {
  const body = makeSample(datasetId, 0, {
    id: sampleId,
    dataset_id: datasetId,
    ...sample,
  });
  await page.route(`**/api/v1/datasets/${datasetId}/samples/${sampleId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

export async function mockSampleAnnotations(
  page: Page,
  datasetId: string,
  sampleId: string,
): Promise<void> {
  await page.route(
    `**/api/v1/datasets/${datasetId}/samples/${sampleId}/annotations`,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    },
  );
}

export async function mockSamplePredictions(
  page: Page,
  datasetId: string,
  sampleId: string,
): Promise<void> {
  await page.route(
    `**/api/v1/datasets/${datasetId}/samples/${sampleId}/predictions`,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    },
  );
}

export async function mockSampleSimilar(
  page: Page,
  datasetId: string,
  sampleId: string,
): Promise<void> {
  await page.route(`**/api/v1/datasets/${datasetId}/samples/${sampleId}/similar`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });
}

export async function mockDatasetQuery(page: Page, datasetId: string): Promise<void> {
  await page.route(`**/api/v1/datasets/${datasetId}/query`, async (route) => {
    const body = route.request().postDataJSON();
    if (body?.query_type === "wafer-points") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          query_type: "wafer-points",
          points: [
            { id: "sample-1", x: 0.1, y: 0.2 },
            { id: "sample-2", x: -0.3, y: 0.5 },
          ],
        }),
      });
    } else {
      await route.continue();
    }
  });
}

export async function mockDatasetStatus(
  page: Page,
  datasetId: string,
  status?: Partial<DatasetStatusResponse>,
): Promise<void> {
  const body: DatasetStatusResponse = {
    allow_train: true,
    train_disabled_reason: null,
    minimum_active_class_count: 2,
    active_class_count: 2,
    annotated_samples: 10,
    total_samples: 10,
    ...status,
  };
  await page.route(`**/api/v1/datasets/${datasetId}/status`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

export async function mockExportDownload(page: Page): Promise<void> {
  await page.route("**/api/v1/download?uri=*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/octet-stream",
      body: Buffer.from("fake-export-binary-data"),
    });
  });
}
