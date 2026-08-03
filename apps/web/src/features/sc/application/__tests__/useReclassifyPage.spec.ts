import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, ref } from "vue";
import { NMessageProvider } from "naive-ui";
import { mountWithProviders, createTestQueryClient } from "@/testing";
import { server } from "@/testing/msw/server";
import { http, HttpResponse } from "msw";
import type { ScDatasetInfo } from "@/features/sc/domain/models";

// ── Mock Orval bulk annotate hook (missing export in generated code) ──
vi.mock("@/generated/orval/endpoints/api", async () => {
  const actual = await vi.importActual<typeof import("@/generated/orval/endpoints/api")>(
    "@/generated/orval/endpoints/api",
  );
  return {
    ...actual,
    useBulkScAnnotationsCreateApiV1DatasetsDatasetIdAnnotationsBulkScPost: () => ({
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
    return h(NMessageProvider, null, {
      default: () => h(ReclassifyPageInner),
    });
  },
});

const mountedWrappers: Array<{ unmount: () => void }> = [];

afterEach(() => {
  for (const wrapper of mountedWrappers.splice(0)) wrapper.unmount();
});

/** Shortcut: mount with pre-seeded query data for the dataset route. */
async function mountPage(
  datasetId: string,
  dataset: ScDatasetInfo,
  extraQueries?: Array<{ key: unknown[]; data: unknown }>,
  annotationStats: Record<string, number> = { Scratch: 1, Clean: 1 },
) {
  const qc = createTestQueryClient();

  server.use(
    http.get("/api/v1/trainers", () =>
      HttpResponse.json([
        {
          id: "resnet50-sc-v1",
          name: "ResNet-50 SC",
          view_type: "patch_image_v1",
          trainable: true,
        },
        {
          id: "yolo-sc-v1",
          name: "YOLO SC",
          view_type: "patch_image_v1",
          trainable: true,
        },
      ]),
    ),
    http.get(`/api/v1/datasets/${datasetId}/annotation-stats`, () =>
      HttpResponse.json({
        total_samples: 10,
        annotated_samples: Object.values(annotationStats).reduce((sum, count) => sum + count, 0),
        unlabeled_samples: 0,
        label_counts: annotationStats,
      }),
    ),
    http.get(`/api/v1/datasets/${datasetId}/status`, () =>
      HttpResponse.json({
        allow_train: true,
        train_disabled_reason: null,
        minimum_active_class_count: 2,
        active_class_count: Object.values(annotationStats).filter((count) => count > 0).length,
        annotated_samples: Object.values(annotationStats).reduce((sum, count) => sum + count, 0),
        total_samples: 10,
      }),
    ),
  );

  // Seed dataset query (Orval query key)
  qc.setQueryData(["api", "v1", "datasets", datasetId], dataset);

  // Seed any extra queries
  for (const { key, data } of extraQueries ?? []) {
    qc.setQueryData(key, data);
  }

  const { wrapper, queryClient } = await mountWithProviders(MakeReclassifyPageWrapper, {
    queryClient: qc,
    routes: [
      {
        path: "/datasets/:id",
        component: MakeReclassifyPageWrapper,
      },
    ],
    initialRoute: `/datasets/${datasetId}`,
  });
  mountedWrappers.push(wrapper);

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

    const added = state.codeLabels.value.find((label) => label.name === "Scratch extra");
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
    expect(state.codeLabels.value.find((label) => label.code === "0")?.shortcut).toBe("");
    expect(state.codeLabels.value.find((label) => label.code === "10")?.shortcut).toBe("1");
  });

  it("treats code 0 as a valid annotation draft", async () => {
    const { state } = await mountPage("ds-test-1", DEFAULT_DATASET);

    state.setAnnotationDraft("D001", "5");
    expect(state.annotationDraft.value.D001).toBe("5");

    state.setAnnotationDraft("D001", "0");
    expect(state.annotationDraft.value.D001).toBe("0");
  });

  it("publishes one draft update when labeling a large selection", async () => {
    const { state } = await mountPage("ds-bulk-draft", DEFAULT_DATASET);
    const defectIds = Array.from({ length: 10_000 }, (_, index) => `D-${index}`);
    const initialDraft = state.annotationDraft.value;

    state.setAnnotationDrafts(defectIds, "5");

    expect(state.annotationDraft.value).not.toBe(initialDraft);
    expect(Object.keys(state.annotationDraft.value)).toHaveLength(10_000);
    expect(state.annotationDraft.value["D-0"]).toBe("5");
    expect(state.annotationDraft.value["D-9999"]).toBe("5");

    const publishedDraft = state.annotationDraft.value;
    state.setAnnotationDrafts(defectIds, "5");
    expect(state.annotationDraft.value).toBe(publishedDraft);
  });
});

describe("useReclassifyPage - train defaults", () => {
  it("selects the first SC trainer by default", async () => {
    const { state } = await mountPage("ds-test-1", DEFAULT_DATASET);

    await waitForCondition(() => state.selectedTrainerId.value === "resnet50-sc-v1");

    expect(state.trainerOptions.value.map((option: { value: string }) => option.value)).toEqual([
      "resnet50-sc-v1",
      "yolo-sc-v1",
    ]);
  });

  it("requires at least two active annotation classes before training", async () => {
    const { state } = await mountPage("ds-test-1", DEFAULT_DATASET, undefined, {
      Scratch: 2,
    });

    await waitForCondition(() => state.selectedTrainerId.value === "resnet50-sc-v1");
    await waitForCondition(() => state.activeClassCount.value === 1);

    expect(state.canTrainAndPredict.value).toBe(false);
  });

  it("explains the per-class training cap and validation pool", async () => {
    const { state } = await mountPage("ds-training-cap", DEFAULT_DATASET, undefined, {
      Scratch: 1_250,
      Particle: 1_100,
    });

    await waitForCondition(() => state.trainingSampleLimitNotice.value !== null);

    expect(state.trainingSampleLimitNotice.value).toContain("at most 1,000 annotations per class");
    expect(state.trainingSampleLimitNotice.value).toContain("350 additional annotations");
    expect(state.trainingSampleLimitNotice.value).toContain("validation pool");
  });

  it("passes the global filter condition to train-and-predict", async () => {
    const trainRequests: Array<Record<string, unknown>> = [];

    server.use(
      http.post("/api/v1/training-jobs/train-and-predict", async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        trainRequests.push(body);
        return HttpResponse.json({
          train_job: { id: "train-job-1", status: "queued" },
          workflow_run_id: "flow-run-1",
        });
      }),
      http.get("/api/v1/training-jobs/train-job-1", () =>
        HttpResponse.json({ id: "train-job-1", status: "queued" }),
      ),
      http.get("/api/v1/prediction-jobs", () => HttpResponse.json([])),
    );

    const { state } = await mountPage("ds-test-1", DEFAULT_DATASET);

    await waitForCondition(() => state.selectedTrainerId.value === "resnet50-sc-v1");
    await waitForCondition(() => state.activeClassCount.value === 2);

    await state.trainAndPredict({
      final_class: { filterType: "set", values: ["Scratch"] },
    });

    expect(trainRequests).toHaveLength(1);
    expect(trainRequests[0]?.sample_filter).toEqual({
      final_class: { filterType: "set", values: ["Scratch"] },
    });
    expect(trainRequests[0]?.sample_ids).toBeUndefined();
  });
});

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
  it("does not start the retired REST gallery pagination pipeline", async () => {
    const requestOffsets: number[] = [];
    server.use(
      http.get("/api/v1/datasets/:id/views/:view/samples", ({ request }) => {
        const url = new URL(request.url);
        const offset = parseInt(url.searchParams.get("offset") ?? "0", 10);
        requestOffsets.push(offset);
        return HttpResponse.json({ items: [], total: 0 });
      }),
    );

    const { state } = await mountPage("ds-perspective-gallery", DEFAULT_DATASET, []);

    await new Promise((resolve) => setTimeout(resolve, 50));

    await state.fetchMoreSamples();
    expect(requestOffsets).toEqual([]);
    expect(state.hasMoreSamples.value).toBe(false);
  });

  it("uses map selection IDs as BlinkTable data source filter", async () => {
    const { state } = await mountPage("ds-filter-query", DEFAULT_DATASET);
    state.handleMapSelectionChange({
      source: "box",
      mode: "append",
      ids: [274, 103],
    });

    expect([...state.mapFilteredIds.value].sort()).toEqual(["274", "103"].sort());
  });

  it("clears the BlinkTable data source filter when the map emits an empty selection", async () => {
    const { state } = await mountPage("ds-box-filter", DEFAULT_DATASET);
    state.handleMapSelectionChange({
      source: "legend",
      mode: "replace",
      ids: [103, 274],
      groupKey: 7,
    });
    state.handleMapSelectionChange({
      source: "clear",
      mode: "clear",
      ids: [],
    });

    expect(state.mapFilteredIds.value.size).toBe(0);
  });
});
