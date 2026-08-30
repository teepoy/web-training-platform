import {
  ref,
  computed,
  watch,
  onBeforeUnmount,
  type Ref,
  type ComputedRef,
  type WritableComputedRef,
} from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import { useMessage } from "naive-ui";
import { toUserMessage } from "@/shared/api/client";

import {
  useGetDatasetApiV1DatasetsDatasetIdGet,
  scBulkCreateAnnotationsApiV1DatasetsDatasetIdAnnotationsBulkScPost,
  useListTrainersRouteApiV1TrainersGet,
  getJobApiV1TrainingJobsJobIdGet,
  getAnnotationStatsApiV1DatasetsDatasetIdAnnotationStatsGet,
  getRevisionApiV1DatasetCollectionsCollectionIdRevisionsRevisionIdGet,
  createTrainAndPredictJobApiV1TrainingJobsTrainAndPredictPost,
} from "@/generated/orval/endpoints/api";
import { listPredictionJobs } from "@/shared/api/predictions";
import type { Trainer } from "@/shared/api/types";
import type {
  DatasetAnnotationStats,
  PredictionJobResponse,
  TrainingJob,
} from "@/generated/orval/models";
import {
  cloneScGlobalFilter,
  emptyScGlobalFilter,
  scGlobalFilterHasConditions,
  toScWorkflowSampleFilter,
  type ScGlobalFilter,
} from "../domain/globalFilter";
import type { ScSamplingProgram } from "../domain/samplingRules";
import type { ScSamplingCandidateScope } from "./inspectionFilterPolicy";
import type { ScSelectionAction } from "../domain/workbenchInteraction";
import { useScReclassifyStore } from "./reclassifyStore";
import type { ScDatasetInfo, ScAnnotationItem } from "../domain/models";
import { DEFAULT_RECLASSIFY_CODE_NAMES } from "./reclassifyCodeNames";
import { loadScSamplingPreference, saveScSamplingPreference } from "./samplingPreferences";

const DEFAULT_SAMPLING_DRAFT_LABEL = "60";

interface WaferGeometryView {
  waferRadiusNm: number;
  centerX: number;
  centerY: number;
  originX: number;
  originY: number;
  dieSizeX: number;
  dieSizeY: number;
}

export interface ReclassifyCodeLabel {
  code: string;
  name: string;
  shortcut: string;
}

export interface ReclassifyPageState {
  datasetId: ComputedRef<string>;
  dataset: ComputedRef<ScDatasetInfo | undefined>;
  isLoading: ComputedRef<boolean>;
  isError: ComputedRef<boolean>;
  errorMessage: ComputedRef<string>;
  annotatedCount: ComputedRef<number>;
  activeClassCount: ComputedRef<number>;
  canTrainAndPredict: ComputedRef<boolean>;
  labelSpace: ComputedRef<string[]>;
  effectiveLabels: ComputedRef<string[]>;
  codeLabels: ComputedRef<ReclassifyCodeLabel[]>;
  shortcutCodeByKey: ComputedRef<Record<string, string>>;
  setLabelShortcut: (code: string, shortcut: string) => void;

  selectedDefectIds: ComputedRef<Set<string>>;
  selectedCount: ComputedRef<number>;
  applySelectionAction: (action: ScSelectionAction) => void;
  clearSelection: () => void;

  waferGeometry: ComputedRef<WaferGeometryView | null>;

  annotationDraft: Ref<Record<string, string>>;
  draftCount: ComputedRef<number>;
  trainingSampleLimitNotice: ComputedRef<string | null>;
  isSubmitting: ComputedRef<boolean>;
  setAnnotationDraft: (defectId: string, label: string) => void;
  setAnnotationDrafts: (defectIds: Iterable<string>, label: string) => void;
  clearDrafts: () => void;
  submitAnnotations: () => void;
  addLabel: (label: string) => void;
  addLabelError: Ref<string | null>;
  isAddingLabel: ComputedRef<boolean>;

  inspectionContext: ComputedRef<{
    inspectionTime: string;
    waferKey: string;
  } | null>;

  showSamplingModal: Ref<boolean>;
  samplingProgram: Ref<ScSamplingProgram>;
  samplingScope: Ref<ScSamplingCandidateScope>;
  assignSampledDraftLabel: Ref<boolean>;
  samplingDraftLabel: Ref<string | null>;
  applySampling: (defectIds: string[]) => void;
  galleryRandomSamplingDefectIds: Ref<Set<string>>;
  clearGalleryRandomSamplingDefectIds: () => void;
  globalFilter: WritableComputedRef<ScGlobalFilter>;
  setGlobalFilter: (filter: ScGlobalFilter) => void;
  clearGlobalFilter: () => void;
  resolveTrainSampleFilter: () => ScGlobalFilter | null;

  selectedTrainerId: Ref<string | null>;
  trainerOptions: ComputedRef<{ label: string; value: string }[]>;
  isTrainPredictRunning: Ref<boolean>;
  trainPredictStatusMessage: Ref<string>;
  trainPredictTaskId: Ref<string | null>;
  trainPredictTrainingStatus: ComputedRef<string>;
  trainPredictPredictionJob: ComputedRef<PredictionJobResponse | null>;
  trainPredictPredictionStatus: ComputedRef<string>;
  trainPredictPredictionPercent: ComputedRef<number | null>;
  trainPredictPredictionProgressLabel: ComputedRef<string>;
  trainPredictPredictionProcessing: ComputedRef<boolean>;
  trainAndPredict: (preparedSampleFilter?: ScGlobalFilter | null) => Promise<void>;
}

export function useReclassifyPage(): ReclassifyPageState {
  const route = useRoute();
  const datasetId = computed(() => route.params.id as string);
  const collectionId = computed(() => {
    const value = route.params.collectionId;
    return typeof value === "string" && value.length > 0 ? value : null;
  });
  const collectionRevisionId = computed(() => {
    const value = route.query.revisionId;
    return typeof value === "string" && value.length > 0 ? value : null;
  });
  const workspaceKey = computed(() =>
    collectionId.value && collectionRevisionId.value
      ? `collection:${collectionId.value}/${collectionRevisionId.value}`
      : datasetId.value,
  );
  const message = useMessage();
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const reclassifyStore = useScReclassifyStore();

  function setGlobalFilter(filter: ScGlobalFilter): void {
    reclassifyStore.setGlobalFilter(workspaceKey.value, filter);
  }

  function clearGlobalFilter(): void {
    reclassifyStore.clearGlobalFilter(workspaceKey.value);
  }

  const globalFilter = computed<ScGlobalFilter>({
    get: () =>
      cloneScGlobalFilter(
        reclassifyStore.globalFiltersByWorkspace?.[workspaceKey.value] ?? emptyScGlobalFilter(),
      ),
    set: setGlobalFilter,
  });
  // ── Dataset ────────────────────────────────────────────────────────

  const datasetQuery = useGetDatasetApiV1DatasetsDatasetIdGet<ScDatasetInfo>(
    computed(() => datasetId.value),
    {
      query: {
        select: (res) => res as ScDatasetInfo,
        retry: false,
      },
    },
  );

  const selectedDataset = computed<ScDatasetInfo | undefined>(() => datasetQuery.data.value);

  const isLoading = computed(() => datasetQuery.isLoading.value);
  const isError = computed(() => datasetQuery.isError.value);
  const errorMessage = computed(
    () => (datasetQuery.error.value as Error)?.message ?? t("sc.datasetLoadFailed"),
  );

  const labelSpace = computed<string[]>(
    () =>
      ((selectedDataset.value?.task_spec as Record<string, unknown> | undefined)?.label_space as
        | string[]
        | undefined) ?? [],
  );

  // InspectionQuad owns SC sample loading and view-only workbench controls. The
  // page owns workflow state, including Global Filter, so outer routes and
  // Train & Predict share one persisted workspace-scoped value.
  const galleryRandomSamplingDefectIds = ref<Set<string>>(
    new Set(reclassifyStore.samplingDefectIdsByDataset?.[workspaceKey.value] ?? []),
  );

  const selectedDefectIds = computed(
    () => new Set(reclassifyStore.selectedDefectIdsByDataset[workspaceKey.value] ?? []),
  );
  const selectedCount = computed(() => selectedDefectIds.value.size);

  function applySelectionAction(action: ScSelectionAction): void {
    if (action.mode === "replace") {
      reclassifyStore.setSelectedDefectIds(workspaceKey.value, action.ids);
    } else if (action.mode === "add") {
      const next = new Set(selectedDefectIds.value);
      for (const id of action.ids) {
        next.add(id);
      }
      reclassifyStore.setSelectedDefectIds(workspaceKey.value, next);
    } else {
      const next = new Set(selectedDefectIds.value);
      for (const id of action.ids) {
        if (next.has(id)) {
          next.delete(id);
        } else {
          next.add(id);
        }
      }
      reclassifyStore.setSelectedDefectIds(workspaceKey.value, next);
    }
  }

  function clearSelection(): void {
    reclassifyStore.clearSelectedDefectIds(workspaceKey.value);
  }

  const annotationStatsQuery = useQuery({
    queryKey: computed(() => ["api", "v1", "datasets", datasetId.value, "annotation-stats"]),
    queryFn: () => getAnnotationStatsApiV1DatasetsDatasetIdAnnotationStatsGet(datasetId.value),
    enabled: computed(() => !!selectedDataset.value),
    retry: false,
  });

  const annotatedCount = computed<number>(() => {
    const stats = annotationStatsQuery.data.value as DatasetAnnotationStats | undefined;
    const annotated = stats?.annotated_samples;
    return typeof annotated === "number" && Number.isFinite(annotated) ? Math.max(0, annotated) : 0;
  });

  const collectionRevisionQuery = useQuery({
    queryKey: computed(() => [
      "dataset-collections",
      collectionId.value,
      "revisions",
      collectionRevisionId.value,
    ]),
    queryFn: () => {
      if (!collectionId.value || !collectionRevisionId.value) {
        throw new Error(t("sc.revisionRequired"));
      }
      return getRevisionApiV1DatasetCollectionsCollectionIdRevisionsRevisionIdGet(
        collectionId.value,
        collectionRevisionId.value,
      );
    },
    enabled: computed(() => !!collectionId.value && !!collectionRevisionId.value),
    retry: false,
  });

  const activeClassCount = computed<number>(() => {
    if (collectionId.value) {
      return Object.values(collectionRevisionQuery.data.value?.label_counts ?? {}).filter(
        (count) => Number(count) > 0,
      ).length;
    }
    const stats = annotationStatsQuery.data.value as DatasetAnnotationStats | undefined;
    const counts = stats?.label_counts ?? {};
    return Object.values(counts).filter((count) => Number(count) > 0).length;
  });

  const inspectionContext = computed<{
    inspectionTime: string;
    waferKey: string;
  } | null>(() => {
    const meta = selectedDataset.value?.dataset_meta;
    const sourceTime = meta?.source_inspection_time;
    const sourceWafer = meta?.source_wafer_key;
    if (
      typeof sourceTime !== "string" ||
      sourceTime.length === 0 ||
      (typeof sourceWafer !== "number" && typeof sourceWafer !== "string")
    ) {
      return null;
    }
    return {
      inspectionTime: sourceTime,
      waferKey: String(sourceWafer),
    };
  });

  const waferGeometry = computed<WaferGeometryView | null>(() => {
    const geometry = selectedDataset.value?.dataset_meta?.geometry;
    if (!geometry || typeof geometry !== "object") return null;
    const g = geometry as Record<string, unknown>;
    return {
      waferRadiusNm: (g.wafer_radius_nm as number) ?? 150_000_000,
      centerX: (g.center_x as number) ?? 0,
      centerY: (g.center_y as number) ?? 0,
      originX: (g.origin_x as number) ?? 0,
      originY: (g.origin_y as number) ?? 0,
      dieSizeX: (g.die_size_x as number) ?? 0,
      dieSizeY: (g.die_size_y as number) ?? 0,
    };
  });

  // ── Annotation draft state (keyed by defectId) ──────────────────────

  const annotationDraft = ref<Record<string, string>>({});
  const pendingLabelNames = ref<string[]>([]);
  const customLabelNames = ref<Record<string, string>>({});
  const customShortcuts = ref<Record<string, string>>({});

  function localStorageKey(kind: "names" | "shortcuts"): string {
    return `sc.reclassify.${kind}.${datasetId.value}`;
  }

  function readLocalRecord(key: string): Record<string, string> {
    try {
      const parsed = JSON.parse(localStorage.getItem(key) ?? "{}");
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
      const out: Record<string, string> = {};
      for (const [rawKey, rawValue] of Object.entries(parsed)) {
        if (typeof rawValue === "string") out[String(rawKey)] = rawValue;
      }
      return out;
    } catch {
      return {};
    }
  }

  function writeLocalRecord(key: string, value: Record<string, string>): void {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {}
  }

  watch(
    datasetId,
    () => {
      customLabelNames.value = readLocalRecord(localStorageKey("names"));
      customShortcuts.value = readLocalRecord(localStorageKey("shortcuts"));
      pendingLabelNames.value = [];
    },
    { immediate: true },
  );

  function defaultShortcutForCode(code: string): string {
    const numeric = Number(code);
    return Number.isInteger(numeric) && numeric >= 0 && numeric <= 8 ? String(numeric + 1) : "";
  }

  const codeLabels = computed<ReclassifyCodeLabel[]>(() => {
    const labels: Array<Omit<ReclassifyCodeLabel, "shortcut">> = Object.entries(
      DEFAULT_RECLASSIFY_CODE_NAMES,
    ).map(([code, name]) => ({
      code,
      name: customLabelNames.value[code] || name,
    }));
    const usedCodes = new Set(labels.map((label) => label.code));
    const existingNames = new Set(labels.map((label) => label.name.toLowerCase()));
    for (const rawLabel of labelSpace.value) {
      const label = String(rawLabel).trim();
      if (!label) continue;
      if (/^\d+$/.test(label) && Number(label) >= 0 && Number(label) <= 60) {
        continue;
      }
      if (existingNames.has(label.toLowerCase())) continue;
      let nextCode = labels.length;
      while (usedCodes.has(String(nextCode))) nextCode += 1;
      const code = String(nextCode);
      usedCodes.add(code);
      existingNames.add(label.toLowerCase());
      labels.push({
        code,
        name: customLabelNames.value[code] || label,
      });
    }
    for (const pendingName of pendingLabelNames.value) {
      const name = pendingName.trim();
      if (!name || existingNames.has(name.toLowerCase())) continue;
      let nextCode = labels.length;
      while (usedCodes.has(String(nextCode))) nextCode += 1;
      const code = String(nextCode);
      usedCodes.add(code);
      existingNames.add(name.toLowerCase());
      labels.push({
        code,
        name,
      });
    }
    for (const [code, rawName] of Object.entries(customLabelNames.value)) {
      const name = rawName.trim();
      if (!name || usedCodes.has(code) || existingNames.has(name.toLowerCase())) {
        continue;
      }
      usedCodes.add(code);
      existingNames.add(name.toLowerCase());
      labels.push({
        code,
        name,
      });
    }
    labels.sort((left, right) => {
      const leftNumber = Number(left.code);
      const rightNumber = Number(right.code);
      if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) {
        return leftNumber - rightNumber;
      }
      return left.code.localeCompare(right.code);
    });
    const explicitShortcutCodes = new Set(Object.keys(customShortcuts.value));
    const usedShortcuts = new Set<string>();
    const effectiveShortcuts: Record<string, string> = {};

    for (const label of labels) {
      const shortcut = customShortcuts.value[label.code]?.trim().slice(0, 1) ?? "";
      const key = shortcut.toLowerCase();
      if (!shortcut || usedShortcuts.has(key)) continue;
      usedShortcuts.add(key);
      effectiveShortcuts[label.code] = shortcut;
    }

    for (const label of labels) {
      if (explicitShortcutCodes.has(label.code)) continue;
      const shortcut = defaultShortcutForCode(label.code);
      const key = shortcut.toLowerCase();
      if (!shortcut || usedShortcuts.has(key)) continue;
      usedShortcuts.add(key);
      effectiveShortcuts[label.code] = shortcut;
    }

    return labels.map((label) => ({
      ...label,
      shortcut: effectiveShortcuts[label.code] ?? "",
    }));
  });

  const shortcutCodeByKey = computed<Record<string, string>>(() => {
    const out: Record<string, string> = {};
    for (const label of codeLabels.value) {
      const shortcut = label.shortcut.trim();
      if (shortcut.length === 1) {
        out[shortcut.toLowerCase()] = label.code;
      }
    }
    return out;
  });

  function setLabelShortcut(code: string, shortcut: string): void {
    const normalized = shortcut.trim().slice(0, 1);
    const next = { ...customShortcuts.value };
    for (const [candidateCode, candidateShortcut] of Object.entries(next)) {
      if (candidateCode !== code && candidateShortcut.toLowerCase() === normalized.toLowerCase()) {
        delete next[candidateCode];
      }
    }
    if (!normalized) {
      delete next[code];
    } else {
      next[code] = normalized;
    }
    customShortcuts.value = next;
    writeLocalRecord(localStorageKey("shortcuts"), next);
  }

  function setAnnotationDrafts(defectIds: Iterable<string>, label: string): void {
    const next = { ...annotationDraft.value };
    let changed = false;
    for (const defectId of defectIds) {
      if (next[defectId] === label) continue;
      next[defectId] = label;
      changed = true;
    }
    if (changed) annotationDraft.value = next;
  }

  function setAnnotationDraft(defectId: string, label: string): void {
    setAnnotationDrafts([defectId], label);
  }

  function clearDrafts(): void {
    annotationDraft.value = {};
  }

  const draftCount = computed(
    () => Object.keys(annotationDraft.value).filter((k) => annotationDraft.value[k]).length,
  );

  const trainingSampleLimitNotice = computed<string | null>(() => {
    const stats = annotationStatsQuery.data.value as DatasetAnnotationStats | undefined;
    const excessCount = Object.values(stats?.label_counts ?? {}).reduce(
      (total, rawCount) => total + Math.max(0, Number(rawCount) - 1_000),
      0,
    );
    if (excessCount === 0) return null;
    return t("sc.trainingSampleLimit", { count: excessCount.toLocaleString() });
  });

  // ── Submit annotations using the stable dataset sample identity ───

  const isSubmittingAnnotations = ref(false);

  function collectionAnnotationTarget(rowKey: string): { datasetId: string; sampleId: string } {
    if (!collectionId.value) {
      return { datasetId: datasetId.value, sampleId: rowKey };
    }
    const sourceDatasetIds = (collectionRevisionQuery.data.value?.source_snapshot ?? [])
      .map((item) => String(item.source_dataset_id ?? ""))
      .filter(Boolean)
      .sort((left, right) => right.length - left.length);
    const sourceDatasetId = sourceDatasetIds.find((id) => rowKey.startsWith(`${id}::`));
    if (!sourceDatasetId) {
      throw new Error(t("sc.collectionRowIdentityMissing", { rowKey }));
    }
    return {
      datasetId: sourceDatasetId,
      sampleId: rowKey.slice(sourceDatasetId.length + 2),
    };
  }

  async function submitAnnotations(): Promise<void> {
    const entries = Object.entries(annotationDraft.value).filter(([, label]) => label);
    if (entries.length === 0) {
      message.warning(t("sc.noAnnotationsToSubmit"));
      return;
    }
    const byDataset = new Map<string, { annotations: ScAnnotationItem[]; rowKeys: string[] }>();
    try {
      for (const [rowKey, label] of entries) {
        const target = collectionAnnotationTarget(rowKey);
        const submission = byDataset.get(target.datasetId) ?? { annotations: [], rowKeys: [] };
        submission.annotations.push({
          sample_id: target.sampleId,
          label,
          annotator: "platform-user",
        });
        submission.rowKeys.push(rowKey);
        byDataset.set(target.datasetId, submission);
      }
      isSubmittingAnnotations.value = true;
      const submissions = [...byDataset.entries()];
      const results = await Promise.allSettled(
        submissions.map(([targetDatasetId, submission]) =>
          scBulkCreateAnnotationsApiV1DatasetsDatasetIdAnnotationsBulkScPost(targetDatasetId, {
            annotations: submission.annotations,
          }),
        ),
      );
      const succeeded = submissions.filter((_, index) => results[index]?.status === "fulfilled");
      const failed = submissions.filter((_, index) => results[index]?.status === "rejected");
      const submittedRowCount = succeeded.reduce(
        (total, [, submission]) => total + submission.rowKeys.length,
        0,
      );
      if (succeeded.length === 0) {
        const firstFailure = results.find((result) => result.status === "rejected");
        throw firstFailure?.reason ?? new Error(t("sc.annotationAllWritesFailed"));
      }
      const nextDraft = { ...annotationDraft.value };
      for (const [, submission] of succeeded) {
        for (const rowKey of submission.rowKeys) delete nextDraft[rowKey];
      }
      annotationDraft.value = nextDraft;
      if (failed.length === 0) {
        pendingLabelNames.value = [];
        message.success(
          t("sc.annotationsApplied", {
            updates: submittedRowCount,
            datasets: succeeded.length,
          }),
        );
      } else {
        message.warning(
          t("sc.annotationsPartiallyApplied", {
            updates: submittedRowCount,
            failures: failed.length,
          }),
        );
      }
      await Promise.all(
        succeeded.flatMap(([targetDatasetId]) => [
          queryClient.invalidateQueries({
            queryKey: ["api", "v1", "datasets", targetDatasetId],
          }),
          queryClient.invalidateQueries({
            queryKey: ["api", "v1", "datasets", targetDatasetId, "status"],
          }),
        ]),
      );
    } catch (error) {
      message.error(toUserMessage(error, t("sc.annotationsCreateFailed")));
    } finally {
      isSubmittingAnnotations.value = false;
    }
  }

  // ── Add label ──────────────────────────────────────────────────────

  const effectiveLabels = computed<string[]>(() => codeLabels.value.map((label) => label.code));

  const addLabelError = ref<string | null>(null);
  const isAddingLabel = computed(() => false);

  function addLabel(newLabel: string) {
    const name = newLabel.trim();
    if (!name) return;
    if (codeLabels.value.some((label) => label.name.toLowerCase() === name.toLowerCase())) {
      addLabelError.value = t("sc.nameAlreadyExists");
      return;
    }
    const usedCodes = new Set(codeLabels.value.map((label) => label.code));
    let nextCodeNumber = codeLabels.value.length;
    while (usedCodes.has(String(nextCodeNumber))) nextCodeNumber += 1;
    const nextCode = String(nextCodeNumber);
    const nextNames = { ...customLabelNames.value, [nextCode]: name };
    customLabelNames.value = nextNames;
    writeLocalRecord(localStorageKey("names"), nextNames);
    addLabelError.value = null;
    pendingLabelNames.value = [...pendingLabelNames.value, name];
  }

  // ── Sampling ───────────────────────────────────────────────────────

  const showSamplingModal = ref(false);
  const samplingProgram = ref(loadScSamplingPreference("annotation"));
  const samplingScope = ref<ScSamplingCandidateScope>("all");
  const assignSampledDraftLabel = ref(true);
  const samplingDraftLabel = ref<string | null>(
    effectiveLabels.value.includes(DEFAULT_SAMPLING_DRAFT_LABEL)
      ? DEFAULT_SAMPLING_DRAFT_LABEL
      : (effectiveLabels.value[0] ?? null),
  );

  watch(effectiveLabels, (labels) => {
    if (!samplingDraftLabel.value || !labels.includes(samplingDraftLabel.value)) {
      samplingDraftLabel.value = labels.includes(DEFAULT_SAMPLING_DRAFT_LABEL)
        ? DEFAULT_SAMPLING_DRAFT_LABEL
        : (labels[0] ?? null);
    }
  });

  watch(samplingProgram, (program) => saveScSamplingPreference("annotation", program), {
    deep: true,
  });

  watch(workspaceKey, (id) => {
    galleryRandomSamplingDefectIds.value = new Set(
      reclassifyStore.samplingDefectIdsByDataset?.[id] ?? [],
    );
  });

  function clearGalleryRandomSamplingDefectIds(): void {
    galleryRandomSamplingDefectIds.value = new Set();
    reclassifyStore.clearSamplingDefectIds(workspaceKey.value);
  }

  function applySampling(defectIds: string[]): void {
    const sampled = Array.from(new Set(defectIds));
    if (sampled.length === 0) return;

    galleryRandomSamplingDefectIds.value = new Set(sampled);
    reclassifyStore.setSamplingDefectIds(workspaceKey.value, sampled);

    if (assignSampledDraftLabel.value && samplingDraftLabel.value) {
      setAnnotationDrafts(sampled, samplingDraftLabel.value);
    }

    showSamplingModal.value = false;
  }

  function resolveTrainSampleFilter(): ScGlobalFilter | null {
    if (!scGlobalFilterHasConditions(globalFilter.value)) return null;
    return cloneScGlobalFilter(globalFilter.value);
  }

  // ── Train & Predict ─────────────────────────────────────────────────

  const selectedTrainerId = ref<string | null>(null);

  const trainersQuery = useListTrainersRouteApiV1TrainersGet({
    query: {
      select: (response) =>
        response.map(
          (item): Trainer => ({
            id: String(item.id ?? ""),
            name: String(item.name ?? ""),
            view_type: String(item.view_type ?? ""),
            trainable: Boolean(item.trainable ?? true),
          }),
        ),
    },
  });

  const trainerOptions = computed<{ label: string; value: string }[]>(() =>
    (trainersQuery.data.value ?? [])
      .filter((t) => t.trainable !== false && t.view_type === "patch_image_v1")
      .map((t) => ({ label: t.name, value: t.id })),
  );

  watch(
    trainerOptions,
    (options) => {
      if (selectedTrainerId.value) return;
      const first = options[0];
      if (first) selectedTrainerId.value = first.value;
    },
    { immediate: true },
  );

  const isTrainPredictRunning = ref(false);
  const trainPredictStatusMessage = ref("");
  const trainPredictTaskId = ref<string | null>(null);

  const trainPredictStatusQuery = useQuery({
    queryKey: computed(() => ["sc", "train-predict-task", trainPredictTaskId.value]),
    queryFn: async () => {
      if (!trainPredictTaskId.value) return null;
      return getJobApiV1TrainingJobsJobIdGet(trainPredictTaskId.value);
    },
    enabled: computed(() => !!trainPredictTaskId.value),
    refetchInterval: computed(() => (isTrainPredictRunning.value ? 1000 : false)),
  });

  const trainPredictTrainingStatus = computed(() =>
    String(trainPredictStatusQuery.data.value?.status ?? "pending").toLowerCase(),
  );

  const trainPredictPredictionJobsQuery = useQuery({
    queryKey: computed(() => [
      "sc",
      "train-predict-prediction-jobs",
      datasetId.value,
      collectionId.value,
      trainPredictTaskId.value,
    ]),
    queryFn: () =>
      listPredictionJobs(collectionId.value ? null : datasetId.value, collectionId.value),
    enabled: computed(() => !!trainPredictTaskId.value),
    refetchInterval: computed(() => (isTrainPredictRunning.value ? 1500 : false)),
  });

  function predictionSummaryValue(job: PredictionJobResponse | null, key: string): number | null {
    const raw = job?.summary?.[key];
    const value = typeof raw === "number" ? raw : Number(raw);
    return Number.isFinite(value) ? value : null;
  }

  const trainPredictPredictionJob = computed<PredictionJobResponse | null>(() => {
    const trainingJobId = trainPredictTaskId.value;
    if (!trainingJobId) return null;
    return (
      (trainPredictPredictionJobsQuery.data.value ?? []).find(
        (job) => job.summary?.source_training_job_id === trainingJobId,
      ) ?? null
    );
  });

  const trainPredictPredictionStatus = computed(() => {
    const job = trainPredictPredictionJob.value;
    if (!job) {
      return trainPredictTrainingStatus.value === "completed" ? "waiting" : "not_started";
    }
    return String(job.status ?? "pending").toLowerCase();
  });

  const trainPredictPredictionPercent = computed<number | null>(() => {
    const job = trainPredictPredictionJob.value;
    const status = trainPredictPredictionStatus.value;
    if (status === "completed") return 100;
    const total = predictionSummaryValue(job, "total_samples");
    const processed = predictionSummaryValue(job, "processed");
    if (!total || processed === null) return null;
    return Math.max(0, Math.min(100, Math.round((processed / total) * 100)));
  });

  const trainPredictPredictionProgressLabel = computed(() => {
    const job = trainPredictPredictionJob.value;
    if (!job) {
      return trainPredictTrainingStatus.value === "completed"
        ? t("sc.waitingForPrediction")
        : t("sc.predictionAfterTraining");
    }
    const total = predictionSummaryValue(job, "total_samples");
    const processed = predictionSummaryValue(job, "processed");
    const successful = predictionSummaryValue(job, "successful");
    const failed = predictionSummaryValue(job, "failed");
    if (total && processed !== null) {
      return t("sc.predictionProgress", {
        processed,
        total,
        successful: successful ?? 0,
        failed: failed ?? 0,
      });
    }
    return t("sc.predictionStatus", { status: trainPredictPredictionStatus.value });
  });

  const trainPredictPredictionProcessing = computed(() => {
    const status = trainPredictPredictionStatus.value;
    return status === "running" || status === "waiting";
  });

  const canTrainAndPredict = computed(
    () => !!selectedTrainerId.value && !isTrainPredictRunning.value && activeClassCount.value >= 2,
  );

  watch(trainPredictStatusQuery.data, (job) => {
    if (!job || !trainPredictTaskId.value) return;
    const status = String(job.status ?? "").toLowerCase();
    const shortId = trainPredictTaskId.value.slice(0, 8);
    if (status === "completed") {
      if (trainPredictPredictionStatus.value === "completed") {
        trainPredictStatusMessage.value = t("sc.workflowCompleted", { id: shortId });
        isTrainPredictRunning.value = false;
      } else {
        trainPredictStatusMessage.value = t("sc.trainingCompletedPredictionStatus", {
          id: shortId,
          status: trainPredictPredictionStatus.value,
        });
        isTrainPredictRunning.value = true;
      }
      return;
    }
    if (status === "failed" || status === "cancelled") {
      trainPredictStatusMessage.value = t("sc.trainingStatus", { id: shortId, status });
      isTrainPredictRunning.value = false;
      return;
    }
    isTrainPredictRunning.value = true;
    trainPredictStatusMessage.value = t("sc.trainingStatus", {
      id: shortId,
      status: status || t("sc.queued"),
    });
  });

  watch(trainPredictPredictionJob, (job) => {
    if (!job || !trainPredictTaskId.value) return;
    const status = String(job.status ?? "").toLowerCase();
    const shortId = trainPredictTaskId.value.slice(0, 8);
    if (status === "completed") {
      trainPredictStatusMessage.value = t("sc.workflowCompleted", { id: shortId });
      isTrainPredictRunning.value = false;
      // InspectionQuad refreshes prediction data from the provider's SSE
      // invalidation; no page-owned sample cache remains to invalidate here.
      return;
    }
    if (status === "failed" || status === "cancelled") {
      trainPredictStatusMessage.value = t("sc.predictionJobStatus", {
        id: job.id.slice(0, 8),
        status,
      });
      isTrainPredictRunning.value = false;
      return;
    }
    if (trainPredictTrainingStatus.value === "completed") {
      trainPredictStatusMessage.value = t("sc.predictionJobStatus", {
        id: job.id.slice(0, 8),
        status: status || t("sc.queued"),
      });
      isTrainPredictRunning.value = true;
    }
  });

  const mounted = ref(true);
  onBeforeUnmount(() => {
    mounted.value = false;
  });

  async function trainAndPredict(preparedSampleFilter?: ScGlobalFilter | null): Promise<void> {
    const trainerId = selectedTrainerId.value;
    if (!trainerId) {
      message.warning(t("sc.selectTrainerFirst"));
      return;
    }
    if (activeClassCount.value < 2) {
      message.warning(t("sc.twoClassesRequired"));
      return;
    }
    if (isTrainPredictRunning.value) return;
    if (trainingSampleLimitNotice.value) {
      message.warning(trainingSampleLimitNotice.value);
    }

    isTrainPredictRunning.value = true;
    trainPredictStatusMessage.value = t("sc.startingWorkflow");

    try {
      if (collectionId.value && !collectionRevisionId.value) {
        throw new Error(t("sc.readyCollectionRequired"));
      }
      const sampleFilter =
        preparedSampleFilter === undefined ? resolveTrainSampleFilter() : preparedSampleFilter;
      const workflow = await createTrainAndPredictJobApiV1TrainingJobsTrainAndPredictPost({
        ...(collectionId.value
          ? {
              collection_id: collectionId.value,
              collection_revision_id: collectionRevisionId.value,
            }
          : { dataset_id: datasetId.value }),
        trainer_id: trainerId,
        target: "image_classification",
        sample_filter: sampleFilter ? toScWorkflowSampleFilter(sampleFilter) : null,
      });
      const trainJobId = typeof workflow.train_job.id === "string" ? workflow.train_job.id : "";
      if (!trainJobId) {
        throw new Error(t("sc.missingTrainingJobId"));
      }
      trainPredictTaskId.value = trainJobId;
      await queryClient.invalidateQueries({
        queryKey: ["jobs", datasetId.value],
      });
      trainPredictStatusMessage.value = t("sc.workflowSubmitted", {
        id: trainJobId.slice(0, 8),
      });
      if (mounted.value) {
        message.success(t("sc.workflowSubmitted", { id: trainJobId.slice(0, 8) }));
      }
    } catch (error: unknown) {
      trainPredictStatusMessage.value = "";
      isTrainPredictRunning.value = false;
      message.error(toUserMessage(error, t("sc.trainPredictFailed")));
    }
  }

  // ── Return ─────────────────────────────────────────────────────────

  return {
    datasetId,
    dataset: selectedDataset,
    isLoading,
    isError,
    errorMessage,
    annotatedCount,
    activeClassCount,
    canTrainAndPredict,
    labelSpace,
    effectiveLabels,
    codeLabels,
    shortcutCodeByKey,
    setLabelShortcut,

    selectedDefectIds,
    selectedCount,
    applySelectionAction,
    clearSelection,

    waferGeometry,

    annotationDraft,
    draftCount,
    trainingSampleLimitNotice,
    isSubmitting: computed(() => isSubmittingAnnotations.value),
    setAnnotationDraft,
    setAnnotationDrafts,
    clearDrafts,
    submitAnnotations,
    addLabel,
    addLabelError,
    isAddingLabel,

    inspectionContext,

    showSamplingModal,
    samplingProgram,
    samplingScope,
    assignSampledDraftLabel,
    samplingDraftLabel,
    applySampling,
    galleryRandomSamplingDefectIds,
    clearGalleryRandomSamplingDefectIds,
    globalFilter,
    setGlobalFilter,
    clearGlobalFilter,
    resolveTrainSampleFilter,

    selectedTrainerId,
    trainerOptions,
    isTrainPredictRunning,
    trainPredictStatusMessage,
    trainPredictTaskId,
    trainPredictTrainingStatus,
    trainPredictPredictionJob,
    trainPredictPredictionStatus,
    trainPredictPredictionPercent,
    trainPredictPredictionProgressLabel,
    trainPredictPredictionProcessing,
    trainAndPredict,
  };
}
