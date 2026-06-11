import { describe, it, expect, vi, beforeEach } from "vitest";
import { defineComponent, h, ref } from "vue";
import { NMessageProvider } from "naive-ui";
import { mountWithProviders, createTestQueryClient } from "@/testing";
import { server } from "@/testing/msw/server";
import { http, HttpResponse } from "msw";
import { create, toBinary } from "@bufbuild/protobuf";
import {
  WaferMapResponseSchema,
} from "@/features/sc/generated/proto/sc/v1/sample_pb";
import type { ScDatasetInfo } from "@/features/sc/domain/models";

// ── Mock Orval bulk annotate hook (missing export in generated code) ──
vi.mock("@/generated/orval/endpoints/api", async () => {
  const actual = await vi.importActual<
    typeof import("@/generated/orval/endpoints/api")
  >("@/generated/orval/endpoints/api");
  return {
    ...actual,
    useBulkScAnnotationsCreateApiV1DatasetsDatasetIdAnnotationsBulkScPost:
      () => ({
        mutate: vi.fn(),
        isPending: ref(false),
        error: ref(null),
      }),
  };
});

import { useReclassifyPage } from "../useReclassifyPage";

const ReclassifyPageInner = defineComponent({
  setup() {
    const state = useReclassifyPage();
    return { state };
  },
  render() {
    return h("div");
  },
});

const MakeReclassifyPageWrapper = defineComponent({
  render() {
    return h(NMessageProvider, null, [h(ReclassifyPageInner)]);
  },
});

/** Shortcut: mount with pre-seeded query data for the dataset route. */
async function mountPage(
  datasetId: string,
  dataset: ScDatasetInfo,
  extraQueries?: Array<{ key: unknown[]; data: unknown }>,
) {
  const qc = createTestQueryClient();

  // Seed dataset query (Orval query key)
  qc.setQueryData(["api", "v1", "datasets", datasetId], {
    data: dataset,
  });

  // Seed any extra queries
  for (const { key, data } of extraQueries ?? []) {
    qc.setQueryData(key, data);
  }

  const { wrapper, queryClient } = await mountWithProviders(
    MakeReclassifyPageWrapper,
    {
      queryClient: qc,
      routes: [
        {
          path: "/datasets/:id",
          component: MakeReclassifyPageWrapper,
        },
      ],
      initialRoute: `/datasets/${datasetId}`,
    },
  );

  await wrapper.vm.$nextTick();

  const inner = wrapper.findComponent(ReclassifyPageInner);
  return {
    wrapper,
    queryClient,
    state: (inner.vm as Record<string, any>).state,
  };
}

const DEFAULT_DATASET: ScDatasetInfo = {
  id: "ds-test-1",
  name: "Test SC Dataset",
  label_space: ["Scratch", "Clean"],
  task_spec: {
    task_type: "sc",
    label_space: ["Scratch", "Clean"],
  },
};

describe("useReclassifyPage - predictionLabels", () => {
  it("maps sample_id to predicted_label", async () => {
    const predictionsData = {
      pages: [
        {
          items: [
            {
              id: "s1",
              latest_prediction: {
                predicted_label: "Scratch",
                confidence: 0.95,
              },
            },
            {
              id: "s2",
              latest_prediction: {
                predicted_label: "Clean",
                confidence: 0.80,
              },
            },
          ],
          total: 2,
        },
      ],
      pageParams: [0],
    };

    const { state } = await mountPage("ds-test-1", DEFAULT_DATASET, [
      {
        key: ["sc", "view-annotations-paged", "ds-test-1"],
        data: predictionsData,
      },
    ]);

    await new Promise((r) => setTimeout(r, 10));
    expect(state.predictionLabels.value["s1"]).toBe("Scratch");
    expect(state.predictionLabels.value["s2"]).toBe("Clean");
  });

  it("returns empty object when predictions are empty", async () => {
    const { state } = await mountPage("ds-test-1", DEFAULT_DATASET, [
      {
        key: ["sc", "view-annotations-paged", "ds-test-1"],
        data: { pages: [{ items: [], total: 0 }], pageParams: [0] },
      },
    ]);

    await new Promise((r) => setTimeout(r, 10));
    expect(Object.keys(state.predictionLabels.value)).toHaveLength(0);
  });
});

describe("useReclassifyPage - dieDisplay", () => {
  it("exposes wafer geometry from plot-points and uses it for reticle die size", async () => {
    const diePoints = [10, 20, 99, 1, 2, 0];
    const { create: createMsg } = await import("@bufbuild/protobuf");
    const { WaferMapResponseSchema: Schema } = await import(
      "@/features/sc/generated/proto/sc/v1/sample_pb"
    );
    const msg = createMsg(Schema, {
      total: 1,
      waferPoints: [150000100, 150000200, 99, 1, 2, 0],
      diePoints,
      geometry: {
        waferRadiusNm: 150000000,
        centerX: 150000000,
        centerY: 150000000,
        originX: -1800000,
        originY: -5990000,
        dieSizeX: 8000000,
        dieSizeY: 8000000,
      },
    });

    const { state } = await mountPage("ds-test-geometry", DEFAULT_DATASET, [
      { key: ["sc", "plot-points", "ds-test-geometry"], data: msg },
    ]);

    await new Promise((r) => setTimeout(r, 10));

    expect(state.waferGeometry.value).toEqual({
      waferRadiusNm: 150000000,
      centerX: 150000000,
      centerY: 150000000,
      originX: -1800000,
      originY: -5990000,
      dieSizeX: 8000000,
      dieSizeY: 8000000,
    });
    expect(state.reticleDieSizeX.value).toBe(8000000);
    expect(state.reticleDieSizeY.value).toBe(8000000);
  });

  it("derives STRIDE=6 die coordinates from diePoints plot data", async () => {
    const diePoints = [5, 7, 1, 0, 1, 0];
    const { fromBinary } = await import("@bufbuild/protobuf");
    const { toBinary, create: createMsg } = await import("@bufbuild/protobuf");
    const { WaferMapResponseSchema: Schema } = await import(
      "@/features/sc/generated/proto/sc/v1/sample_pb"
    );
    const msg = createMsg(Schema, {
      total: 1,
      waferPoints: diePoints,
      diePoints,
    });

    const { state } = await mountPage("ds-test-1", DEFAULT_DATASET, [
      { key: ["sc", "plot-points", "ds-test-1"], data: msg },
    ]);

    await new Promise((r) => setTimeout(r, 10));
    const dieArr = state.dieDisplay.value;
    // STRIDE=6: 6 elements for 1 point
    expect(dieArr.length).toBe(6);
    expect(dieArr[0]).toBe(5);
    expect(dieArr[1]).toBe(7);
    expect(dieArr[2]).toBe(1);
    expect(dieArr[3]).toBe(0);
    expect(dieArr[4]).toBe(1);
    expect(dieArr[5]).toBe(0);
  });

  it("preserves class, rough, and review fields in STRIDE=6 dieDisplay", async () => {
    const diePoints = [10, 20, 99, 1, 2, 3, 30, 40, 88, 4, 5, 6];
    const { create: createMsg } = await import("@bufbuild/protobuf");
    const { WaferMapResponseSchema: Schema } = await import(
      "@/features/sc/generated/proto/sc/v1/sample_pb"
    );
    const msg = createMsg(Schema, {
      total: 2,
      waferPoints: diePoints,
      diePoints,
    });

    const { state } = await mountPage("ds-test-2", DEFAULT_DATASET, [
      { key: ["sc", "plot-points", "ds-test-2"], data: msg },
    ]);

    await new Promise((r) => setTimeout(r, 10));
    const dieArr = state.dieDisplay.value;
    // STRIDE=6: 12 elements for 2 points
    expect(dieArr.length).toBe(12);
    // point 0: class=99, rough=1, review=2
    expect(dieArr[2]).toBe(99);
    expect(dieArr[3]).toBe(1);
    expect(dieArr[4]).toBe(2);
    // point 1: class=88, rough=4, review=5
    expect(dieArr[8]).toBe(88);
    expect(dieArr[9]).toBe(4);
    expect(dieArr[10]).toBe(5);
  });
});

describe("useReclassifyPage - reticleDisplay", () => {
  it("derives STRIDE=6 reticle coordinates from reticlePoints plot data", async () => {
    const reticlePoints = [5, 7, 1, 0, 1, 0];
    const { create: createMsg } = await import("@bufbuild/protobuf");
    const { WaferMapResponseSchema: Schema } = await import(
      "@/features/sc/generated/proto/sc/v1/sample_pb"
    );
    const msg = createMsg(Schema, {
      total: 1,
      waferPoints: reticlePoints,
      diePoints: reticlePoints,
      reticlePoints,
    });

    const { state } = await mountPage("ds-test-1", DEFAULT_DATASET, [
      { key: ["sc", "plot-points", "ds-test-1"], data: msg },
    ]);

    await new Promise((r) => setTimeout(r, 10));
    const retArr = state.reticleDisplay.value;
    expect(retArr.length).toBe(6);
    expect(retArr[0]).toBe(5);
    expect(retArr[1]).toBe(7);
    expect(retArr[2]).toBe(1);
    expect(retArr[3]).toBe(0);
    expect(retArr[4]).toBe(1);
    expect(retArr[5]).toBe(0);
  });

  it("caps reticleDisplay at 10000 points", async () => {
    const totalPoints = 15000;
    const pts = Array.from({ length: totalPoints * 6 }, (_, i) => i % 100);
    const { create: createMsg } = await import("@bufbuild/protobuf");
    const { WaferMapResponseSchema: Schema } = await import(
      "@/features/sc/generated/proto/sc/v1/sample_pb"
    );
    const msg = createMsg(Schema, {
      total: totalPoints,
      waferPoints: pts,
      diePoints: pts,
      reticlePoints: pts,
    });

    const { state } = await mountPage("ds-test-cap", DEFAULT_DATASET, [
      { key: ["sc", "plot-points", "ds-test-cap"], data: msg },
    ]);

    await new Promise((r) => setTimeout(r, 10));
    expect(state.reticleDisplay.value.length).toBe(10000 * 6);
  });
});

describe("useReclassifyPage - map zoom", () => {
  it("filters each map with its own coordinate viewport", async () => {
    const { create: createMsg } = await import("@bufbuild/protobuf");
    const { WaferMapResponseSchema: Schema } = await import(
      "@/features/sc/generated/proto/sc/v1/sample_pb"
    );
    const msg = createMsg(Schema, {
      total: 2,
      waferPoints: [10, 10, 1, 0, 0, 0, 100, 100, 2, 0, 0, 0],
      diePoints: [5, 5, 1, 0, 0, 0, 50, 50, 2, 0, 0, 0],
      reticlePoints: [20, 20, 1, 0, 0, 0, 200, 200, 2, 0, 0, 0],
    });

    const { state } = await mountPage("ds-test-zoom", DEFAULT_DATASET, [
      { key: ["sc", "plot-points", "ds-test-zoom"], data: msg },
    ]);

    state.setMapZoom({ x: 0, y: 0, w: 20, h: 20 });
    expect(state.waferDisplay.value).toEqual([10, 10, 1, 0, 0, 0]);
    expect(state.dieDisplay.value).toHaveLength(12);

    state.setActiveMapTab("die");
    state.setMapZoom({ x: 40, y: 40, w: 20, h: 20 });
    expect(state.dieDisplay.value).toEqual([50, 50, 2, 0, 0, 0]);
    expect(state.waferDisplay.value).toEqual([10, 10, 1, 0, 0, 0]);

    state.setActiveMapTab("reticle");
    state.setMapZoom({ x: 150, y: 150, w: 100, h: 100 });
    expect(state.reticleDisplay.value).toEqual([200, 200, 2, 0, 0, 0]);
  });
});

describe("useReclassifyPage - addLabel", () => {
  it("rejects duplicate label", async () => {
    const datasetWithLabels: ScDatasetInfo = {
      ...DEFAULT_DATASET,
      label_space: ["Scratch", "Clean"],
      task_spec: {
        ...DEFAULT_DATASET.task_spec,
        label_space: ["Scratch", "Clean"],
      },
    };

    const { state } = await mountPage("ds-test-1", datasetWithLabels);

    state.addLabel("Scratch");
    await new Promise((r) => setTimeout(r, 50));

    const errMsg = state.addLabelError.value;
    expect(errMsg).toBeTruthy();
    expect(errMsg.toLowerCase()).toContain("already exists");
  });
});

function makeFakePlotPointsBytes(sampleCount: number): Uint8Array {
  const pts = Array.from({ length: sampleCount * 6 }, (_, i) => i % 100);
  const msg = create(WaferMapResponseSchema, {
    total: sampleCount,
    waferPoints: pts,
    diePoints: pts,
  });
  return toBinary(WaferMapResponseSchema, msg);
}

function makeViewSampleRows(count: number, offset = 0) {
  return Array.from({ length: count }, (_, i) => ({
    sample_id: `s${offset + i}`,
    inspection_time: "2025-01-01T00:00:00",
    wafer_key: 1,
    defect_id: String(offset + i + 1),
    wafer_x: 100 * (offset + i),
    wafer_y: 200 * (offset + i),
    die_x: (offset + i) % 10,
    die_y: (offset + i) % 8,
    rough_bin: (offset + i) % 5,
    class_number: (offset + i) % 3,
    review_images: [],
    images: [],
  }));
}

describe("useReclassifyPage - split plotPointsQuery / sampleRowsInfiniteQuery", () => {
  const DATASET_ID = "ds-split-1";

  beforeEach(() => {
    server.use(
      http.get("/api/v1/sc/datasets/:id/plot-points", () => {
        return new HttpResponse(makeFakePlotPointsBytes(1000), {
          status: 200,
          headers: { "Content-Type": "application/x-protobuf" },
        });
      }),
      http.get("/api/v1/datasets/:id/views/:view/samples", ({ request }) => {
        const url = new URL(request.url);
        const offset = parseInt(url.searchParams.get("offset") ?? "0", 10);
        return HttpResponse.json({
          items: makeViewSampleRows(200, offset),
          total: 1000,
        });
      }),
      http.get("/api/v1/datasets/:id/samples-with-labels", ({ request }) => {
        const url = new URL(request.url);
        const offset = parseInt(url.searchParams.get("offset") ?? "0", 10);
        return HttpResponse.json({
          items: Array.from({ length: 200 }, (_, i) => ({
            id: `s${offset + i}`,
            latest_annotation: null,
          })),
          total: 1000,
        });
      }),
    );
  });

  it("plotPointsQuery yields 1000 samples — waferDisplay length equals 6000", async () => {
    const bytes = makeFakePlotPointsBytes(1000);
    const { fromBinary } = await import("@bufbuild/protobuf");
    const decoded = fromBinary(WaferMapResponseSchema, bytes);

    const { state } = await mountPage(DATASET_ID, DEFAULT_DATASET, [
      { key: ["sc", "plot-points", DATASET_ID], data: decoded },
    ]);

    await new Promise((r) => setTimeout(r, 20));

    expect(state.waferDisplay.value.length).toBe(6000);
  });

  it("plotPointTotal equals 1000 from first sampleRowsInfiniteQuery page", async () => {
    const { state } = await mountPage(DATASET_ID, DEFAULT_DATASET, [
      {
        key: ["sc", "view-samples-paged", DATASET_ID, "id"],
        data: {
          pages: [{ items: makeViewSampleRows(200), total: 1000 }],
          pageParams: [0],
        },
      },
    ]);

    await new Promise((r) => setTimeout(r, 20));
    expect(state.plotPointTotal.value).toBe(1000);
  });

  it("hasMoreSamples is true when loaded rows are less than total", async () => {
    const { state } = await mountPage(DATASET_ID, DEFAULT_DATASET, [
      {
        key: ["sc", "view-samples-paged", DATASET_ID, "id"],
        data: {
          pages: [{ items: makeViewSampleRows(200), total: 1000 }],
          pageParams: [0],
        },
      },
    ]);

    await new Promise((r) => setTimeout(r, 20));
    expect(state.hasMoreSamples.value).toBe(true);
  });

  it("classNumberOptions derives from plotPoints packed array (not paginated rows)", async () => {
    const { state } = await mountPage(DATASET_ID, DEFAULT_DATASET, []);

    await new Promise((r) => setTimeout(r, 50));

    expect(state.classNumberOptions.value.length).toBeGreaterThan(0);
  });

  it("fetchMoreSamples triggers second request with offset > 0", async () => {
    const requestOffsets: number[] = [];
    server.use(
      http.get("/api/v1/datasets/:id/views/:view/samples", ({ request }) => {
        const url = new URL(request.url);
        const offset = parseInt(url.searchParams.get("offset") ?? "0", 10);
        requestOffsets.push(offset);
        return HttpResponse.json({
          items: makeViewSampleRows(200, offset),
          total: 1000,
        });
      }),
    );

    const { state } = await mountPage(DATASET_ID, DEFAULT_DATASET, []);

    await new Promise((r) => setTimeout(r, 100));

    const countBefore = requestOffsets.filter((o) => o === 0).length;
    expect(countBefore).toBeGreaterThan(0);

    await state.fetchMoreSamples();
    await new Promise((r) => setTimeout(r, 100));

    const secondPageOffsets = requestOffsets.filter((o) => o > 0);
    expect(secondPageOffsets.length).toBeGreaterThan(0);
    expect(secondPageOffsets[0]).toBe(200);
  });

  it("uses map box-selection IDs as the reclassify selection", async () => {
    const { state } = await mountPage("ds-filter-query", DEFAULT_DATASET);
    state.handleBoxSelectionChange([274, 103]);

    expect([...state.selectedDefectIds.value]).toEqual(["274", "103"]);
    expect([...state.mapSelectedDefectIds.value]).toEqual([274, 103]);
  });

  it("clears the reclassify selection when the map emits an empty selection", async () => {
    const { state } = await mountPage("ds-box-filter", DEFAULT_DATASET);
    state.handleBoxSelectionChange([103, 274]);
    state.handleBoxSelectionChange([]);

    expect(state.selectedDefectIds.value.size).toBe(0);
  });
});
