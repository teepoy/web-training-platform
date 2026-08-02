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

describe("useReclassifyPage - selection actions", () => {
  it("applies replace, add and toggle actions to the annotation selection", async () => {
    const { state } = await mountPage("ds-selection", DEFAULT_DATASET);

    state.applySelectionAction({
      source: "sample-table",
      ids: ["103"],
      mode: "replace",
    });
    state.applySelectionAction({ source: "blink-table", ids: ["274"], mode: "add" });
    state.applySelectionAction({ source: "blink-table", ids: ["103"], mode: "toggle" });

    expect([...state.selectedDefectIds.value]).toEqual(["274"]);
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

describe("useReclassifyPage - review sampling", () => {
  it("keeps existing drafts and assigns the explicitly selected sampling label", async () => {
    const { state } = await mountPage("ds-sampling", DEFAULT_DATASET);
    state.annotationDraft.value = { existing: "7" };
    state.assignDefaultDraftLabel.value = true;
    state.samplingDraftLabel.value = "12";

    state.applySampling(["103", "274", "103"]);

    expect([...state.galleryRandomSamplingDefectIds.value]).toEqual(["103", "274"]);
    expect(state.annotationDraft.value).toEqual({ existing: "7", "103": "12", "274": "12" });
  });

  it("clears the active cohort explicitly", async () => {
    const { state } = await mountPage("ds-clear-sampling", DEFAULT_DATASET);
    state.applySampling(["3", "9"]);

    state.clearGalleryRandomSamplingDefectIds();

    expect(state.galleryRandomSamplingDefectIds.value.size).toBe(0);
  });

  it("combines the active cohort with Global Filter for Train & Predict", async () => {
    const { state } = await mountPage("ds-sampled-train", DEFAULT_DATASET);
    state.applySampling(["3", "9"]);

    expect(
      state.resolveTrainSampleFilter({
        final_class: { filterType: "set", values: ["Scratch"] },
      }),
    ).toEqual({
      final_class: { filterType: "set", values: ["Scratch"] },
      defect_id: { filterType: "set", values: ["3", "9"] },
    });
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
    const { state } = await mountPage("ds-test-1", DEFAULT_DATASET, {
      Scratch: 2,
    });

    await waitForCondition(() => state.selectedTrainerId.value === "resnet50-sc-v1");
    await waitForCondition(() => state.activeClassCount.value === 1);

    expect(state.canTrainAndPredict.value).toBe(false);
  });

  it("explains the per-class training cap and validation pool", async () => {
    const { state } = await mountPage("ds-training-cap", DEFAULT_DATASET, {
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
