import { describe, it, expect, vi, beforeEach } from "vitest";
import { defineComponent, h, ref } from "vue";
import { NMessageProvider } from "naive-ui";
import { mountWithProviders, createTestQueryClient } from "@/testing";
import { server } from "@/testing/msw/server";
import { http, HttpResponse } from "msw";
import { create, toBinary } from "@bufbuild/protobuf";
import { WaferMapResponseSchema } from "@/features/sc/generated/proto/sc/v1/sample_pb";
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
    const viewSamplesData = {
      pages: [
        {
          items: [
            {
              sample_id: "s1",
              defect_id: "s1",
              inspection_time: "2026-01-01T00:00:00",
              wafer_key: 1,
              wafer_x: 0,
              wafer_y: 0,
              die_x: 0,
              die_y: 0,
              rough_bin: 1,
              class_number: 1,
              images: [],
              predicted_label: "Scratch",
              confidence: 0.95,
            },
            {
              sample_id: "s2",
              defect_id: "s2",
              inspection_time: "2026-01-01T00:00:00",
              wafer_key: 1,
              wafer_x: 0,
              wafer_y: 0,
              die_x: 0,
              die_y: 0,
              rough_bin: 1,
              class_number: 1,
              images: [],
              predicted_label: "Clean",
              confidence: 0.8,
            },
          ],
          total: 2,
        },
      ],
      pageParams: [0],
    };

    const { state } = await mountPage("ds-test-1", DEFAULT_DATASET, [
      {
        key: ["sc", "view-samples-paged", "ds-test-1", null],
        data: viewSamplesData,
      },
    ]);

    await new Promise((r) => setTimeout(r, 10));
    expect(state.predictionLabels.value["s1"]).toBe("Scratch");
    expect(state.predictionLabels.value["s2"]).toBe("Clean");
  });

  it("returns empty object when predictions are empty", async () => {
    const emptySamplesData = {
      pages: [
        {
          items: [
            {
              sample_id: "s1",
              defect_id: "s1",
              inspection_time: "2026-01-01T00:00:00",
              wafer_key: 1,
              wafer_x: 0,
              wafer_y: 0,
              die_x: 0,
              die_y: 0,
              rough_bin: 1,
              class_number: 1,
              images: [],
              predicted_label: "",
              confidence: null,
            },
          ],
          total: 1,
        },
      ],
      pageParams: [0],
    };

    const { state } = await mountPage("ds-test-1", DEFAULT_DATASET, [
      {
        key: ["sc", "view-samples-paged", "ds-test-1", null],
        data: emptySamplesData,
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
    const { WaferMapResponseSchema: Schema } =
      await import("@/features/sc/generated/proto/sc/v1/sample_pb");
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
    const { WaferMapResponseSchema: Schema } =
      await import("@/features/sc/generated/proto/sc/v1/sample_pb");
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
    const { WaferMapResponseSchema: Schema } =
      await import("@/features/sc/generated/proto/sc/v1/sample_pb");
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
    const { WaferMapResponseSchema: Schema } =
      await import("@/features/sc/generated/proto/sc/v1/sample_pb");
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
});

describe("useReclassifyPage - addLabel", () => {
  beforeEach(() => {
    localStorage.clear();
  });

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

  it("keeps code/name combos in frontend state and exposes code annotations", async () => {
    const datasetWithoutLabels: ScDatasetInfo = {
      ...DEFAULT_DATASET,
      label_space: [],
      task_spec: {
        ...DEFAULT_DATASET.task_spec,
        label_space: [],
      },
    };
    const { state } = await mountPage("ds-test-1", datasetWithoutLabels);

    expect(state.codeLabels.value).toHaveLength(61);
    expect(state.codeLabels.value[0]).toMatchObject({
      code: "0",
      name: "Unclassified",
      shortcut: "1",
    });
    expect(state.effectiveLabels.value.slice(0, 3)).toEqual(["0", "1", "2"]);

    state.addLabel("Scratch extra");
    await new Promise((r) => setTimeout(r, 10));

    const added = state.codeLabels.value.find(
      (label) => label.name === "Scratch extra",
    );
    expect(added).toBeTruthy();
    expect(added?.code).toBe("61");
    expect(state.effectiveLabels.value).toContain("61");
  });

  it("lets users remap single-key shortcuts", async () => {
    const { state } = await mountPage("ds-test-1", DEFAULT_DATASET);

    state.setLabelShortcut("10", "q");
    await new Promise((r) => setTimeout(r, 10));

    expect(state.shortcutCodeByKey.value.q).toBe("10");
  });

  it("keeps annotation shortcuts exclusive across default and custom keys", async () => {
    const { state } = await mountPage("ds-test-1", DEFAULT_DATASET);

    expect(state.shortcutCodeByKey.value["1"]).toBe("0");

    state.setLabelShortcut("10", "1");
    await new Promise((r) => setTimeout(r, 10));

    expect(state.shortcutCodeByKey.value["1"]).toBe("10");
    expect(
      state.codeLabels.value.find((label) => label.code === "0")?.shortcut,
    ).toBe("");
    expect(
      state.codeLabels.value.find((label) => label.code === "10")?.shortcut,
    ).toBe("1");
  });

  it("treats code 0 as clearing a draft annotation", async () => {
    const { state } = await mountPage("ds-test-1", DEFAULT_DATASET);

    state.setAnnotationDraft("D001", "5");
    expect(state.annotationDraft.value.D001).toBe("5");

    state.setAnnotationDraft("D001", "0");
    expect(state.annotationDraft.value.D001).toBeUndefined();
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

function makeInt32Bytes(values: number[]): ArrayBuffer {
  const buffer = new ArrayBuffer(values.length * 4);
  const view = new DataView(buffer);
  values.forEach((value, index) => view.setInt32(index * 4, value, true));
  return buffer;
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

async function waitForCondition(condition: () => boolean, timeoutMs = 1000) {
  const startedAt = Date.now();
  while (!condition()) {
    if (Date.now() - startedAt > timeoutMs) {
      throw new Error("Timed out waiting for condition");
    }
    await new Promise((r) => setTimeout(r, 10));
  }
}

describe("useReclassifyPage - split plotPointsQuery / sampleRowsInfiniteQuery", () => {
  const DATASET_ID = "ds-split-1";

  beforeEach(() => {
    server.use(
      http.get("/api/v1/sc/datasets/:id/plot-points/stream", () => {
        return new HttpResponse(
          [
            'event: progress\ndata: {"event_type":"progress","operation":"sc.plot-points","status":"loading","message":"Preparing plot points"}\n\n',
            'event: done\ndata: {"event_type":"done"}\n\n',
          ].join(""),
          {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          },
        );
      }),
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

  it("waits for real defect ids before loading samples to avoid an offset duplicate", async () => {
    const sampleRequests: Array<{
      offset: string | null;
      sampleIds: string | null;
    }> = [];
    server.use(
      http.get("/api/v1/sc/datasets/:id/defect-ids.bin", async () => {
        await new Promise((r) => setTimeout(r, 30));
        return new HttpResponse(makeInt32Bytes([1, 2, 3]), {
          status: 200,
          headers: { "Content-Type": "application/octet-stream" },
        });
      }),
      http.get("/api/v1/datasets/:id/views/:view/samples", ({ request }) => {
        const url = new URL(request.url);
        sampleRequests.push({
          offset: url.searchParams.get("offset"),
          sampleIds: url.searchParams.get("sampleIds"),
        });
        return HttpResponse.json({
          items: makeViewSampleRows(3),
          total: 3,
        });
      }),
    );

    await mountPage("ds-real-ids", DEFAULT_DATASET, []);

    await waitForCondition(() => sampleRequests.length > 0);

    expect(sampleRequests.every((req) => req.offset === null)).toBe(true);
    expect(sampleRequests[0]?.sampleIds).toBe("1,2,3");
  });

  it("loads additional real-id pages with sample_ids instead of stopping at the first 200", async () => {
    const requestSampleIds: string[] = [];
    server.use(
      http.get("/api/v1/sc/datasets/:id/defect-ids.bin", () => {
        return new HttpResponse(
          makeInt32Bytes(Array.from({ length: 450 }, (_, i) => i + 1)),
          {
            status: 200,
            headers: { "Content-Type": "application/octet-stream" },
          },
        );
      }),
      http.get("/api/v1/datasets/:id/views/:view/samples", ({ request }) => {
        const url = new URL(request.url);
        const sampleIds = url.searchParams.get("sampleIds") ?? "";
        requestSampleIds.push(sampleIds);
        const ids = sampleIds.split(",").filter(Boolean).map(Number);
        return HttpResponse.json({
          items: ids.map((id) => ({
            ...makeViewSampleRows(1, id - 1)[0],
            sample_id: `s${id}`,
            defect_id: String(id),
          })),
          total: 450,
        });
      }),
    );

    const { state } = await mountPage("ds-real-ids-paged", DEFAULT_DATASET, []);

    await waitForCondition(() => state.hasMoreSamples.value);
    await state.fetchMoreSamples();
    await waitForCondition(() => requestSampleIds.length >= 2);

    expect(requestSampleIds[0]?.split(",")[0]).toBe("1");
    expect(requestSampleIds[0]?.split(",")).toHaveLength(200);
    expect(requestSampleIds[1]?.split(",")[0]).toBe("201");
    expect(requestSampleIds[1]?.split(",")).toHaveLength(200);
  });

  it("uses map box-selection IDs as BlinkTable data source filter", async () => {
    const { state } = await mountPage("ds-filter-query", DEFAULT_DATASET);
    state.handleBoxSelectionChange([274, 103]);

    expect([...state.mapFilteredIds.value].sort()).toEqual(
      ["274", "103"].sort(),
    );
  });

  it("clears the BlinkTable data source filter when the map emits an empty selection", async () => {
    const { state } = await mountPage("ds-box-filter", DEFAULT_DATASET);
    state.handleBoxSelectionChange([103, 274]);
    state.handleBoxSelectionChange([]);

    expect(state.mapFilteredIds.value.size).toBe(0);
  });
});
