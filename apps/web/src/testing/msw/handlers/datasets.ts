import { http, HttpResponse } from "msw";
import { makeDataset, makeDatasets } from "../factories/dataset.factory";
import type { Dataset } from "@/generated/orval/models/dataset";

/** In-memory store for datasets created during tests */
const store = new Map<string, Dataset>();

/** Reset the in-memory store between tests */
export function resetDatasetStore() {
  store.clear();
}

export const listDatasetsHandler = http.get("/api/v1/datasets", () => {
  const datasets = store.size > 0 ? Array.from(store.values()) : makeDatasets(0);
  return HttpResponse.json(datasets);
});

export const createDatasetHandler = http.post(
  "/api/v1/datasets",
  async ({ request }) => {
    const body = (await request.json()) as Partial<Dataset>;
    const dataset = makeDataset({
      ...body,
      id: `dataset-${Date.now()}`,
      created_at: new Date().toISOString(),
    });
    store.set(dataset.id!, dataset);
    return HttpResponse.json(dataset, { status: 201 });
  },
);

export const getDatasetHandler = http.get(
  "/api/v1/datasets/:datasetId",
  ({ params }) => {
    const { datasetId } = params;
    const cached = store.get(datasetId as string);
    if (cached) {
      return HttpResponse.json(cached);
    }
    const dataset = makeDataset({ id: datasetId as string });
    return HttpResponse.json(dataset);
  },
);

export const deleteDatasetHandler = http.delete(
  "/api/v1/datasets/:datasetId",
  ({ params }) => {
    const { datasetId } = params;
    store.delete(datasetId as string);
    return HttpResponse.json(null, { status: 204 });
  },
);

export const datasetHandlers = [
  listDatasetsHandler,
  createDatasetHandler,
  getDatasetHandler,
  deleteDatasetHandler,
];
