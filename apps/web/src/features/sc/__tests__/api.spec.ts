import { describe, it, expect, beforeEach } from "vitest";
import { server } from "@/testing/msw/server";
import { http, HttpResponse } from "msw";

import {
  getInspectionsApiV1ScInspectionsGet,
  listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet,
} from "@/generated/orval/endpoints/api";
import {
  getGetInspectionsApiV1ScInspectionsGetUrl,
  getListViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGetUrl,
} from "@/generated/orval/endpoints/api";

let lastRequestUrl: string;
let lastRequestMethod: string;

function capturedPathAndQuery(): string {
  const url = new URL(lastRequestUrl);
  return url.pathname + url.search;
}

beforeEach(() => {
  lastRequestUrl = "";
  lastRequestMethod = "";

  const capture = ({ request }: { request: Request }) => {
    lastRequestUrl = request.url;
    lastRequestMethod = request.method;
    return HttpResponse.json({ items: [], total: 0 });
  };

  server.use(
    http.get("/api/v1/sc/inspections", capture),
    http.get(
      "/api/v1/datasets/:datasetId/views/patch_image_v1/samples",
      capture,
    ),
    http.get(
      "/api/v1/datasets/:datasetId/views/review_image_v1/samples",
      capture,
    ),
    http.get(
      "/api/v1/datasets/:datasetId/views/not_real/samples",
      () => {
        return HttpResponse.json(
          { detail: "Unsupported view type: not_real" },
          { status: 422 },
        );
      },
    ),
  );
});

describe("getInspectionsApiV1ScInspectionsGet", () => {
  it("calls the API with correct inspection URL and query params", async () => {
    const params = {
      start_time: "2025-01-01T00:00:00Z",
      end_time: "2025-12-31T23:59:59Z",
    };
    await getInspectionsApiV1ScInspectionsGet(params);

    const expectedUrl = getGetInspectionsApiV1ScInspectionsGetUrl(params);
    expect(capturedPathAndQuery()).toBe(expectedUrl);
    expect(lastRequestMethod).toBe("GET");
  });
});

describe("listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet (patch_image_v1)", () => {
  it("calls the API with correct URL for patch_image_v1 view", async () => {
    const datasetId = "ds-42";
    const viewType = "patch_image_v1";

    await listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet(
      datasetId,
      viewType,
    );

    const expectedUrl =
      getListViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGetUrl(
        datasetId,
        viewType,
      );
    expect(capturedPathAndQuery()).toBe(expectedUrl);
    expect(lastRequestMethod).toBe("GET");
  });

  it("appends offset and limit pagination params", async () => {
    const datasetId = "ds-42";
    const viewType = "patch_image_v1";
    const params = { offset: 0, limit: 100 };

    await listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet(
      datasetId,
      viewType,
      params,
    );

    const expectedUrl =
      getListViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGetUrl(
        datasetId,
        viewType,
        params,
      );
    expect(capturedPathAndQuery()).toBe(expectedUrl);
  });

  it("does not append params when both offset and limit are undefined", async () => {
    const datasetId = "ds-99";
    const viewType = "patch_image_v1";

    await listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet(
      datasetId,
      viewType,
    );

    const expectedUrl =
      getListViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGetUrl(
        datasetId,
        viewType,
      );
    expect(capturedPathAndQuery()).toBe(expectedUrl);
    expect(capturedPathAndQuery()).not.toContain("offset");
    expect(capturedPathAndQuery()).not.toContain("limit");
  });
});

describe("listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet (review_image_v1)", () => {
  it("calls the API with correct URL for review_image_v1 view", async () => {
    const datasetId = "ds-42";
    const viewType = "review_image_v1";

    await listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet(
      datasetId,
      viewType,
    );

    const expectedUrl =
      getListViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGetUrl(
        datasetId,
        viewType,
      );
    expect(capturedPathAndQuery()).toBe(expectedUrl);
    expect(lastRequestMethod).toBe("GET");
  });
});

describe("listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet (invalid view type)", () => {
  it("throws error for unsupported view type: not_real", async () => {
    const datasetId = "ds-42";
    const viewType = "not_real";

    await expect(
      listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet(
        datasetId,
        viewType,
      ),
    ).rejects.toThrow("Unsupported view type");
  });
});
