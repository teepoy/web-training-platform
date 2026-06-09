import {
  ref,
  computed,
  watch,
  onBeforeUnmount,
  type Ref,
  type ComputedRef,
} from "vue";
import { useRoute } from "vue-router";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/vue-query";
import { useMessage } from "naive-ui";
import { buildBlinkTableData } from "@/shared/utils/blink-table-data";
import type { BlinkSampleInput } from "@/shared/utils/blink-table-data";
import type { AnnotationGridItem } from "@/shared/types/components";
import { listSamplesWithLabels } from "@/shared/api/samples";
import {
  useGetDatasetApiV1DatasetsDatasetIdGet,
  useScBulkCreateAnnotationsApiV1DatasetsDatasetIdAnnotationsBulkScPost,
  type ScBulkCreateAnnotationsApiV1DatasetsDatasetIdAnnotationsBulkScPostMutationResult,
  listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet,
  useListTrainersRouteApiV1TrainersGet,
  createTrainingJobApiV1TrainingJobsPost,
  getJobApiV1TrainingJobsJobIdGet,
} from "@/generated/orval/endpoints/api";
import { runPredictions, getPredictionJob } from "@/shared/api/predictions";
import type { Trainer } from "@/shared/api/types";
import type { TrainingJob } from "@/generated/orval/models";
import { fetchScPlotPoints } from "../api/plotPoints";
import { fetchScDatasetClassList } from "../api/classList";
import {
  fetchScDatasetBoxFilter,
  type ScBoxRegion,
  type ScMapMode,
} from "../api/boxFilter";
import type { ClassList } from "../generated/proto/sc/v1/sample_pb";
import {
  DEFAULT_RETICLE_MAP_OPTIONS,
  normalizeReticleMapOptions,
  type ReticleMapOptions,
} from "./reticleMapOptions";
import { useScReclassifyStore } from "./reclassifyStore";
import type { ScDatasetInfo, ScAnnotationItem } from "../domain/models";
import {
  scPatchUrl,
  scReviewUrl,
  normalizeScImageRole,
} from "../domain/models";

interface WaferGeometryView {
  waferRadiusNm: number;
  centerX: number;
  centerY: number;
  originX: number;
  originY: number;
  dieSizeX: number;
  dieSizeY: number;
}

type MapMode = "wafer" | "die" | "reticle";
type MapViewport = { x: number; y: number; w: number; h: number };

function filterPackedPoints(
  points: number[],
  viewport: MapViewport | null,
  limit = 10000,
): number[] {
  const result: number[] = [];
  const maxX = viewport ? viewport.x + viewport.w : 0;
  const maxY = viewport ? viewport.y + viewport.h : 0;
  const count = packedPointCount(points);

  for (let i = 0; i < count && result.length < limit * 6; i += 1) {
    const offset = i * 6;
    const x = points[offset];
    const y = points[offset + 1];
    if (
      viewport &&
      (x < viewport.x || x > maxX || y < viewport.y || y > maxY)
    ) {
      continue;
    }
    result.push(
      x,
      y,
      points[offset + 2],
      points[offset + 3],
      points[offset + 4],
      points[offset + 5],
    );
  }
  return result;
}

interface ScViewImage {
  role: string;
  image_id: string;
  image_type?: string;
  content_type?: string;
  url: string;
}

interface ScViewRow {
  sample_id: string;
  inspection_time: string;
  wafer_key: number;
  defect_id: string | number;
  wafer_x: number;
  wafer_y: number;
  die_x: number;
  die_y: number;
  rough_bin: number;
  class_number: number;
  review_images?: Array<{ image_id: number }>;
  images?: ScViewImage[];
}

interface ScViewRowsPage {
  items: ScViewRow[];
  total: number;
}

interface SampleLabelItem {
  id: string;
  latest_annotation?: {
    label?: string | null;
  } | null;
  latest_prediction?: {
    predicted_label?: string | null;
    confidence?: number | null;
  } | null;
}

interface SampleLabelsPage {
  items: SampleLabelItem[];
  total: number;
}

export interface ReclassifySampleImage {
  role: string;
  imageId: string;
  url: string;
}

export interface ReclassifySample {
  sampleId: string;
  inspectionTime: string;
  waferKey: number;
  defectId: string;
  waferX: number;
  waferY: number;
  dieX: number;
  dieY: number;
  roughBin: number;
  classNumber: number;
  reviewImageIds: number[];
  images: ReclassifySampleImage[];
  currentLabel: string | null;
}

export type SelectionMode = "replace" | "add" | "toggle";

export interface ReclassifyPageState {
  datasetId: ComputedRef<string>;
  dataset: ComputedRef<ScDatasetInfo | undefined>;
  isLoading: ComputedRef<boolean>;
  isError: ComputedRef<boolean>;
  errorMessage: ComputedRef<string>;
  scSamples: ComputedRef<ReclassifySample[]>;
  isBlinkLoading: ComputedRef<boolean>;
  isMapLoading: ComputedRef<boolean>;
  samplesError: ComputedRef<string | null>;
  fetchMoreSamples: () => Promise<unknown>;
  hasMoreSamples: ComputedRef<boolean>;
  isFetchingMoreSamples: ComputedRef<boolean>;
  plotPointTotal: ComputedRef<number>;
  annotatedCount: ComputedRef<number>;
  labelSpace: ComputedRef<string[]>;
  effectiveLabels: ComputedRef<string[]>;
  labelOptions: ComputedRef<string[]>;
  classNumberOptions: ComputedRef<string[]>;
  classList: ComputedRef<ClassList | null>;

  activeMapTab: Ref<MapMode>;
  mapZoom: ComputedRef<MapViewport | null>;
  setActiveMapTab: (mode: MapMode) => void;
  setMapZoom: (viewport: MapViewport | null) => void;
  waferDisplay: ComputedRef<number[]>;
  waferFilterIds: Ref<string[] | null>;
  mapFilterCount: ComputedRef<number>;
  applyMapBoxFilter: (mode: ScMapMode, region: ScBoxRegion) => Promise<void>;
  selectedDefectIds: ComputedRef<Set<string>>;
  mapSelectedDefectIds: ComputedRef<Set<number>>;
  selectedCount: ComputedRef<number>;
  selectDefectIds: (ids: string[], mode: SelectionMode) => void;
  clearSelection: () => void;
  filteredScSamples: ComputedRef<ReclassifySample[]>;

  waferGeometry: ComputedRef<WaferGeometryView | null>;
  dieDisplay: ComputedRef<number[]>;
  dieFullPoints: ComputedRef<Array<[number, number, number]>>;
  dieRenderPoints: ComputedRef<Array<[number, number]>>;
  reticleDisplay: ComputedRef<number[]>;
  reticleXDieCount: ComputedRef<number>;
  reticleYDieCount: ComputedRef<number>;
  reticleDieSizeX: ComputedRef<number>;
  reticleDieSizeY: ComputedRef<number>;
  reticleOptions: ComputedRef<ReticleMapOptions>;
  updateReticleOptions: (options: ReticleMapOptions) => void;
  isReticleMapLoading: ComputedRef<boolean>;
  reticleMapError: ComputedRef<string | null>;

  blinkTableData: ComputedRef<{
    rows: import("@/shared/types/blink-table").BlinkRow[];
    columns: import("@/shared/types/blink-table").BlinkColumnDef[];
  }>;

  annotationGridItems: ComputedRef<AnnotationGridItem[]>;
  annotationDraft: Ref<Record<string, string>>;
  draftCount: ComputedRef<number>;
  isSubmitting: ComputedRef<boolean>;
  setAnnotationDraft: (defectId: string, label: string) => void;
  clearDrafts: () => void;
  submitAnnotations: () => void;
  addLabel: (label: string) => void;
  addLabelError: Ref<string | null>;
  isAddingLabel: ComputedRef<boolean>;

  predictionLabels: ComputedRef<Record<string, string>>;
  predictionConfidences: ComputedRef<Record<string, number | null>>;
  isPredictionsLoading: ComputedRef<boolean>;

  activeTab: Ref<"blink" | "map">;
  inspectionContext: ComputedRef<{
    inspectionTime: string;
    waferKey: string;
  } | null>;

  showSamplingModal: Ref<boolean>;
  samplingCount: Ref<number>;
  assignDefaultDraftLabel: Ref<boolean>;
  applySampling: () => void;

  selectedTrainerId: Ref<string | null>;
  trainerOptions: ComputedRef<{ label: string; value: string }[]>;
  isTrainPredictRunning: Ref<boolean>;
  trainPredictStatusMessage: Ref<string>;
  trainAndPredict: () => Promise<void>;
}

function scImageUrlForRole(row: ScViewRow, image: ScViewImage): string {
  const rawRole = (image.role || image.image_type || "").toLowerCase();
  if (rawRole === "review") {
    const imageId = Number(image.image_id);
    return Number.isFinite(imageId)
      ? scReviewUrl(row.inspection_time, row.wafer_key, row.defect_id, imageId)
      : "";
  }
  const patchRole = normalizeScImageRole(rawRole);
  if (patchRole) {
    return scPatchUrl(
      row.inspection_time,
      row.wafer_key,
      row.defect_id,
      patchRole,
    );
  }
  return "";
}

function packedPointCount(points: number[]): number {
  return Math.floor(points.length / 6);
}

function packedPointOptions(points: number[], fieldOffset: 3 | 4): string[] {
  const values = new Set<number>();
  const count = packedPointCount(points);
  for (let i = 0; i < count; i += 1) {
    const value = points[i * 6 + fieldOffset];
    if (Number.isFinite(value)) values.add(value);
  }
  return [...values].sort((a, b) => a - b).map(String);
}

export function useReclassifyPage(): ReclassifyPageState {
  const route = useRoute();
  const datasetId = computed(() => route.params.id as string);
  const message = useMessage();
  const queryClient = useQueryClient();
  const reclassifyStore = useScReclassifyStore();

  // ── Dataset ────────────────────────────────────────────────────────

  const datasetQuery = useGetDatasetApiV1DatasetsDatasetIdGet<ScDatasetInfo>(
    computed(() => datasetId.value),
    {
      query: {
        select: (res) => res.data as ScDatasetInfo,
        retry: false,
      },
    },
  );

  const selectedDataset = computed<ScDatasetInfo | undefined>(
    () => datasetQuery.data.value,
  );

  const isLoading = computed(() => datasetQuery.isLoading.value);
  const isError = computed(() => datasetQuery.isError.value);
  const errorMessage = computed(
    () =>
      (datasetQuery.error.value as Error)?.message ?? "Failed to load dataset",
  );

  const labelSpace = computed<string[]>(
    () =>
      ((selectedDataset.value?.task_spec as Record<string, unknown> | undefined)
        ?.label_space as string[] | undefined) ?? [],
  );

  // ── Dataset-scoped samples (SC patch_image_v1 view) ────────────────

  const pageSize = 200;
  const waferFilterIds = ref<string[] | null>(null);
  const sampleFilterKey = computed(() =>
    waferFilterIds.value?.length
      ? [...waferFilterIds.value].sort().join(",")
      : "",
  );

  const reticleOptionsState = ref<ReticleMapOptions>({
    ...DEFAULT_RETICLE_MAP_OPTIONS,
  });
  const reticleOptions = computed<ReticleMapOptions>(() =>
    normalizeReticleMapOptions(reticleOptionsState.value),
  );

  const plotPointsQuery = useQuery({
    queryKey: computed(() => ["sc", "plot-points", datasetId.value]),
    queryFn: () => fetchScPlotPoints(datasetId.value, reticleOptions.value),
    enabled: computed(() => !!selectedDataset.value),
    retry: false,
  });
  const classListQuery = useQuery({
    queryKey: computed(() => ["sc", "class-list", datasetId.value]),
    queryFn: () => fetchScDatasetClassList(datasetId.value),
    enabled: computed(() => !!selectedDataset.value),
    retry: false,
  });
  const classList = computed(() => classListQuery.data.value ?? null);

  const sampleRowsInfiniteQuery = useInfiniteQuery({
    queryKey: computed(() => [
      "sc",
      "view-samples-paged",
      datasetId.value,
      sampleFilterKey.value,
    ]),
    initialPageParam: 0,
    queryFn: async ({ pageParam }: { pageParam: number }) => {
      const resp =
        await listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet(
          datasetId.value,
          "patch_image_v1",
          {
            offset: pageParam,
            limit: pageSize,
            sampleIds: sampleFilterKey.value || undefined,
          },
        );
      return (resp.data ?? { items: [], total: 0 }) as ScViewRowsPage;
    },
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((n, p) => n + p.items.length, 0);
      return loaded < lastPage.total ? loaded : undefined;
    },
    enabled: computed(() => !!selectedDataset.value),
    retry: false,
  });

  // ── Annotation join ────────────────────────────────────────────────

  const annotationsInfiniteQuery = useInfiniteQuery({
    queryKey: computed(() => ["sc", "view-annotations-paged", datasetId.value]),
    initialPageParam: 0,
    queryFn: ({ pageParam }: { pageParam: number }) =>
      listSamplesWithLabels(
        datasetId.value,
        pageParam,
        pageSize,
        undefined,
        "id",
        true,
      ) as Promise<SampleLabelsPage>,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((n, p) => n + p.items.length, 0);
      return loaded < lastPage.total ? loaded : undefined;
    },
    enabled: computed(() => !!selectedDataset.value),
    retry: false,
  });

  const annotationLabels = computed(() => {
    const map = new Map<string, string>();
    for (const [label, group] of Object.entries(classList.value?.labels ?? {})) {
      for (const defectId of group.defectIds) {
        map.set(String(defectId), label);
      }
    }
    if (map.size > 0) return map;
    for (const page of annotationsInfiniteQuery.data.value?.pages ?? []) {
      for (const item of page.items ?? []) {
        const label = item.latest_annotation?.label;
        if (label) map.set(item.id, label);
      }
    }
    return map;
  });

  const loadedRows = computed<ScViewRow[]>(() => {
    return (
      sampleRowsInfiniteQuery.data.value?.pages ?? []
    ).flatMap((page) => page.items);
  });

  const scSamples = computed<ReclassifySample[]>(() => {
    const rows = loadedRows.value;
    const labels = annotationLabels.value;
    return rows.map((r) => ({
      sampleId: r.sample_id,
      inspectionTime: r.inspection_time,
      waferKey: r.wafer_key,
      defectId: String(r.defect_id),
      waferX: r.wafer_x,
      waferY: r.wafer_y,
      dieX: r.die_x,
      dieY: r.die_y,
      roughBin: r.rough_bin,
      classNumber: r.class_number,
      reviewImageIds: (r.review_images ?? []).map((ri) => ri.image_id),
      images: (r.images ?? []).map((img) => ({
        role: img.role || img.image_type || "image",
        imageId: img.image_id,
        url: scImageUrlForRole(r, img),
      })),
      currentLabel: labels.get(String(r.defect_id)) ?? null,
    }));
  });

  const isBlinkLoading = computed(
    () =>
      sampleRowsInfiniteQuery.isLoading.value ||
      annotationsInfiniteQuery.isLoading.value,
  );

  const isMapLoading = computed(
    () => plotPointsQuery.isLoading.value,
  );
  const samplesError = computed<string | null>(
    () =>
      (plotPointsQuery.error.value as Error)?.message ??
      (classListQuery.error.value as Error)?.message ??
      (sampleRowsInfiniteQuery.error.value as Error)?.message ??
      (annotationsInfiniteQuery.error.value as Error)?.message ??
      null,
  );

  const hasMoreSamples = computed(
    () => sampleRowsInfiniteQuery.hasNextPage.value ?? false,
  );
  const isFetchingMoreSamples = computed(
    () => sampleRowsInfiniteQuery.isFetchingNextPage.value,
  );

  const plotPointTotal = computed<number>(
    () =>
      sampleRowsInfiniteQuery.data.value?.pages?.[0]?.total ??
      scSamples.value.length,
  );

  const annotatedCount = computed<number>(
    () => Object.values(classList.value?.labels ?? {})
      .reduce((count, group) => count + group.count, 0),
  );

  async function fetchMoreSamples(): Promise<unknown> {
    if (
      sampleRowsInfiniteQuery.isFetching.value ||
      sampleRowsInfiniteQuery.isFetchingNextPage.value
    )
      return undefined;

    const rowResult = sampleRowsInfiniteQuery.hasNextPage.value
      ? sampleRowsInfiniteQuery.fetchNextPage()
      : Promise.resolve(undefined);
    const annotationResult = annotationsInfiniteQuery.hasNextPage.value
      ? annotationsInfiniteQuery.fetchNextPage()
      : Promise.resolve(undefined);
    return Promise.all([rowResult, annotationResult]);
  }

  // ── Inspection context (derived from first sample, display-only) ───

  const inspectionContext = computed<{
    inspectionTime: string;
    waferKey: string;
  } | null>(() => {
    const first = loadedRows.value[0];
    if (!first) {
      const plot = plotPointsQuery.data.value;
      if (!plot) return null;
      return {
        inspectionTime: "",
        waferKey: String(plot.waferKey),
      };
    }
    return {
      inspectionTime: first.inspection_time,
      waferKey: String(first.wafer_key),
    };
  });

  // ── Label options ───────────────────────────────────────────────────

  const roughBinOptions = computed(() => {
    const values = Object.keys(classList.value?.roughBins ?? {});
    if (values.length > 0) return values.sort((a, b) => Number(a) - Number(b));
    return packedPointOptions(plotPointsQuery.data.value?.waferPoints ?? [], 4);
  });

  const labelOptions = computed(() => {
    if (labelSpace.value.length > 0) return labelSpace.value;
    return roughBinOptions.value;
  });

  const classNumberOptions = computed(() => {
    const values = Object.keys(classList.value?.classNumbers ?? {})
      .sort((a, b) => Number(a) - Number(b));
    if (values.length === 0) {
      const pointValues = packedPointOptions(
        plotPointsQuery.data.value?.waferPoints ?? [],
        3,
      );
      return pointValues.length > 0 ? pointValues : labelOptions.value;
    }
    return values.length > 0 ? values : labelOptions.value;
  });

  const predictionLabels = computed<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    for (const [label, group] of Object.entries(
      classList.value?.prediction ?? {},
    )) {
      for (const defectId of group.defectIds) {
        map[String(defectId)] = label;
      }
    }
    if (Object.keys(map).length > 0) return map;
    for (const page of annotationsInfiniteQuery.data.value?.pages ?? []) {
      for (const item of page.items ?? []) {
        const label = (item.latest_prediction as Record<string, unknown> | null | undefined)?.predicted_label as string | null | undefined;
        if (label) map[item.id] = label;
      }
    }
    return map;
  });

  const predictionConfidences = computed<Record<string, number | null>>(() => {
    const map: Record<string, number | null> = {};
    for (const page of annotationsInfiniteQuery.data.value?.pages ?? []) {
      for (const item of page.items ?? []) {
        const conf = ((item.latest_prediction as Record<string, unknown> | null | undefined)?.confidence ?? null) as number | null;
        map[item.id] = conf;
      }
    }
    return map;
  });

  const isPredictionsLoading = computed(() => false);

  // ── Flat display arrays ─────────────────────────────────────────────

  const activeMapTab = ref<MapMode>("wafer");
  const mapZoomByMode = ref<Record<MapMode, MapViewport | null>>({
    wafer: null,
    die: null,
    reticle: null,
  });
  const mapZoom = computed(() => mapZoomByMode.value[activeMapTab.value]);

  function setActiveMapTab(mode: MapMode): void {
    activeMapTab.value = mode;
  }

  function setMapZoom(viewport: MapViewport | null): void {
    mapZoomByMode.value = {
      ...mapZoomByMode.value,
      [activeMapTab.value]: viewport,
    };
  }

  const waferDisplay = computed(() =>
    filterPackedPoints(
      plotPointsQuery.data.value?.waferPoints ?? [],
      mapZoomByMode.value.wafer,
    ),
  );

  const dieDisplay = computed(() =>
    filterPackedPoints(
      plotPointsQuery.data.value?.diePoints ?? [],
      mapZoomByMode.value.die,
    ),
  );

  const dieFullPoints = computed<Array<[number, number, number]>>(() => {
    const src = dieDisplay.value;
    const out: Array<[number, number, number]> = [];
    for (let i = 0; i + 5 < src.length; i += 6) {
      out.push([src[i], src[i + 1], src[i + 2]]);
    }
    return out;
  });

  const dieRenderPoints = computed<Array<[number, number]>>(() => {
    const full = dieFullPoints.value;
    const limit = Math.min(full.length, 10000);
    const out: Array<[number, number]> = new Array(limit);
    for (let i = 0; i < limit; i += 1) out[i] = [full[i][0], full[i][1]];
    return out;
  });

  const waferGeometry = computed<WaferGeometryView | null>(() => {
    const geometry = plotPointsQuery.data.value?.geometry;
    if (!geometry) return null;
    return {
      waferRadiusNm: geometry.waferRadiusNm,
      centerX: geometry.centerX,
      centerY: geometry.centerY,
      originX: geometry.originX,
      originY: geometry.originY,
      dieSizeX: geometry.dieSizeX,
      dieSizeY: geometry.dieSizeY,
    };
  });

  const inferredReticleDieSizeX = computed(() => {
    let maxDieX = 0;
    for (const point of dieFullPoints.value)
      maxDieX = Math.max(maxDieX, point[0]);
    return Math.max(1, Math.ceil(maxDieX || 100000));
  });
  const inferredReticleDieSizeY = computed(() => {
    let maxDieY = 0;
    for (const point of dieFullPoints.value)
      maxDieY = Math.max(maxDieY, point[1]);
    return Math.max(1, Math.ceil(maxDieY || 100000));
  });

  // ── Tab state ──────────────────────────────────────────────────────

  const activeTab = ref<"blink" | "map">("blink");

  const reticleXDieCount = computed(() => reticleOptions.value.xDieCount);
  const reticleYDieCount = computed(() => reticleOptions.value.yDieCount);
  const reticleDieSizeX = computed(
    () => waferGeometry.value?.dieSizeX ?? inferredReticleDieSizeX.value,
  );
  const reticleDieSizeY = computed(
    () => waferGeometry.value?.dieSizeY ?? inferredReticleDieSizeY.value,
  );

  function updateReticleOptions(options: ReticleMapOptions): void {
    reticleOptionsState.value = normalizeReticleMapOptions(options);
    void plotPointsQuery.refetch();
  }

  const reticleDisplay = computed(() =>
    filterPackedPoints(
      plotPointsQuery.data.value?.reticlePoints ?? [],
      mapZoomByMode.value.reticle,
    ),
  );
  const reticleMapError = computed<string | null>(() => null);

  // ── Wafer filter state (keyed by defectId string) ──────────────────

  const filteredScSamples = computed<ReclassifySample[]>(() => scSamples.value);
  const mapFilterCount = computed(() => waferFilterIds.value?.length ?? 0);

  async function applyMapBoxFilter(
    mode: ScMapMode,
    region: ScBoxRegion,
  ): Promise<void> {
    try {
      const result = await fetchScDatasetBoxFilter(
        datasetId.value,
        mode,
        region,
        reticleOptions.value,
      );
      const next = new Set(waferFilterIds.value ?? []);
      for (const defectId of result.defect_ids) next.add(defectId);
      waferFilterIds.value = next.size > 0 ? [...next] : null;
    } catch (error) {
      message.error(
        (error as Error)?.message ?? "Failed to filter samples by map box",
      );
    }
  }

  // ── Selection state (Blink table box-selection, separate from filter) ─

  const selectedDefectIds = computed(
    () => new Set(reclassifyStore.selectedDefectIdsByDataset[datasetId.value] ?? []),
  );
  const mapSelectedDefectIds = computed(
    () =>
      new Set(
        (waferFilterIds.value ?? []).map(Number).filter(Number.isFinite),
      ),
  );

  const selectedCount = computed(() => selectedDefectIds.value.size);

  function selectDefectIds(ids: string[], mode: SelectionMode): void {
    if (mode === "replace") {
      reclassifyStore.setSelectedDefectIds(datasetId.value, ids);
    } else if (mode === "add") {
      const next = new Set(selectedDefectIds.value);
      for (const id of ids) {
        next.add(id);
      }
      reclassifyStore.setSelectedDefectIds(datasetId.value, next);
    } else {
      // toggle
      const next = new Set(selectedDefectIds.value);
      for (const id of ids) {
        if (next.has(id)) {
          next.delete(id);
        } else {
          next.add(id);
        }
      }
      reclassifyStore.setSelectedDefectIds(datasetId.value, next);
    }
  }

  function clearSelection(): void {
    reclassifyStore.clearSelectedDefectIds(datasetId.value);
  }

  // ── Annotation draft state (keyed by defectId) ──────────────────────

  const annotationDraft = ref<Record<string, string>>({});
  const pendingLabels = ref<string[]>([]);

  function setAnnotationDraft(defectId: string, label: string): void {
    annotationDraft.value = { ...annotationDraft.value, [defectId]: label };
  }

  function clearDrafts(): void {
    annotationDraft.value = {};
  }

  const draftCount = computed(
    () =>
      Object.keys(annotationDraft.value).filter((k) => annotationDraft.value[k])
        .length,
  );

  // ── Helper: use dataset-owned image URLs only ───────────────────────

  function imageUrlByRole(
    s: ReclassifySample,
    role: "template" | "defective" | "difference",
  ): string {
    const matched = s.images.find((img) =>
      img.role.toLowerCase().includes(role),
    );
    return matched?.url ?? "";
  }

  // ── Annotation grid items ───────────────────────────────────────────

  const annotationGridItems = computed<AnnotationGridItem[]>(() => {
    const selected = selectedDefectIds.value;
    if (selected.size === 0) return [];
    return scSamples.value
      .filter((s) => selected.has(s.defectId))
      .map((s) => ({
        id: s.defectId,
        imageSrcs: [
          imageUrlByRole(s, "template"),
          imageUrlByRole(s, "defective"),
          imageUrlByRole(s, "difference"),
        ].filter((url) => url.length > 0),
        currentLabel: s.currentLabel,
        draftLabel: annotationDraft.value[s.defectId] ?? null,
        predictionLabel: predictionLabels.value[s.defectId] ?? null,
        predictionConfidence: predictionConfidences.value[s.defectId] ?? null,
        predictionId: null,
        metadata: {
          defectId: s.defectId,
          waferX: s.waferX,
          waferY: s.waferY,
          roughBin: s.roughBin,
          classNumber: s.classNumber,
        },
      }));
  });

  // ── Blink table data ────────────────────────────────────────────────

  const BLINK_ROLE_ORDER = [
    "patch_template",
    "patch_defective",
    "patch_difference",
  ];

  function orderedImageUrls(images: ReclassifySampleImage[]): string[] {
    const byRole = new Map<string, ReclassifySampleImage[]>();
    for (const img of images) {
      const key = (img.role || "image").toLowerCase();
      const bucket = byRole.get(key) ?? [];
      bucket.push(img);
      byRole.set(key, bucket);
    }
    const out: string[] = [];
    for (const role of BLINK_ROLE_ORDER) {
      for (const img of byRole.get(role) ?? []) out.push(img.url);
      byRole.delete(role);
    }
    for (const bucket of byRole.values()) {
      for (const img of bucket) out.push(img.url);
    }
    return out;
  }

  const blinkTableData = computed(() => {
    const blinkInputs: BlinkSampleInput[] = filteredScSamples.value.map((s) => {
      const urls = orderedImageUrls(s.images).filter((url) => url.length > 0);
      return {
        id: s.defectId,
        imageSrcs: urls,
        metadata: {
          defectId: s.defectId,
          waferX: s.waferX,
          waferY: s.waferY,
          roughBin: s.roughBin,
          classNumber: s.classNumber,
        },
        label: annotationDraft.value[s.defectId] ?? undefined,
      };
    });
    return buildBlinkTableData(blinkInputs);
  });

  // ── Submit annotations (SC-specific endpoint, defect_id-based) ─────

  const bulkAnnotateMutation =
    useScBulkCreateAnnotationsApiV1DatasetsDatasetIdAnnotationsBulkScPost({
      mutation: {
        onSuccess: (
          data: ScBulkCreateAnnotationsApiV1DatasetsDatasetIdAnnotationsBulkScPostMutationResult,
        ) => {
          const created = (data.data as { created: number }).created;
          message.success(`Created ${created} annotations`);
          annotationDraft.value = {};
          pendingLabels.value = [];
          void queryClient.refetchQueries({
            queryKey: ["sc", "view-annotations-paged", datasetId.value],
          });
          void queryClient.refetchQueries({
            queryKey: ["sc", "plot-points", datasetId.value],
          });
          void queryClient.refetchQueries({
            queryKey: ["sc", "class-list", datasetId.value],
          });
          void queryClient.refetchQueries({
            queryKey: ["sc", "view-samples-paged", datasetId.value],
          });
          void queryClient.refetchQueries({
            queryKey: ["api", "v1", "datasets", datasetId.value],
          });
        },
        onError: (err: Error) => {
          message.error(err.message ?? "Failed to create annotations");
        },
      },
    });

  function submitAnnotations(): void {
    const entries = Object.entries(annotationDraft.value).filter(
      ([, label]) => label,
    );
    if (entries.length === 0) {
      message.warning("No annotations to submit");
      return;
    }
    bulkAnnotateMutation.mutate({
      datasetId: datasetId.value,
      data: {
        annotations: entries.map<ScAnnotationItem>(([defect_id, label]) => ({
          defect_id,
          label,
          annotator: "platform-user",
        })),
      },
    });
  }

  // ── Add label ──────────────────────────────────────────────────────

  const effectiveLabels = computed<string[]>(() => {
    const combined = new Set<string>(labelSpace.value);
    for (const label of pendingLabels.value) {
      combined.add(label);
    }
    return [...combined];
  });

  watch(
    [effectiveLabels, () => !!selectedDataset.value] as const,
    ([labels, hasDataset]) => {
      if (hasDataset && labels.length === 0) {
        pendingLabels.value = ["1", "2", "3", "4", "5", "6", "7", "8", "9"];
      }
    },
  );

  const addLabelError = ref<string | null>(null);
  const isAddingLabel = computed(() => false);

  function addLabel(newLabel: string) {
    if (!newLabel) return;
    if (labelSpace.value.includes(newLabel)) {
      addLabelError.value = "Label already exists";
      return;
    }
    if (pendingLabels.value.includes(newLabel)) return;
    addLabelError.value = null;
    pendingLabels.value = [...pendingLabels.value, newLabel];
  }

  // ── Sampling ───────────────────────────────────────────────────────

  const showSamplingModal = ref(false);
  const samplingCount = ref(200);
  const assignDefaultDraftLabel = ref(false);
  async function applySampling(): Promise<void> {
    const count = samplingCount.value;
    if (count <= 0) return;

    const resp =
      await listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet(
        datasetId.value,
        "patch_image_v1",
        { order_by: "random", limit: count },
      );
    const data = (resp.data ?? { items: [], total: 0 }) as ScViewRowsPage;
    const sampled = data.items.map((row) => String(row.defect_id));
    if (sampled.length === 0) return;

    waferFilterIds.value = sampled;

    if (assignDefaultDraftLabel.value) {
      const firstLabel = effectiveLabels.value[0];
      if (firstLabel) {
        const next: Record<string, string> = {};
        for (const id of sampled) {
          next[id] = firstLabel;
        }
        annotationDraft.value = next;
      }
    }

    showSamplingModal.value = false;
  }

  // ── Train & Predict ─────────────────────────────────────────────────

  const selectedTrainerId = ref<string | null>(null);

  const trainersQuery = useListTrainersRouteApiV1TrainersGet({
    query: {
      select: (response) =>
        (response.data ?? []).map(
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

  const isTrainPredictRunning = ref(false);
  const trainPredictStatusMessage = ref("");

  const mounted = ref(true);
  onBeforeUnmount(() => {
    mounted.value = false;
  });

  async function trainAndPredict(): Promise<void> {
    const trainerId = selectedTrainerId.value;
    if (!trainerId) {
      message.warning("Please select a trainer first");
      return;
    }
    if (isTrainPredictRunning.value) return;

    isTrainPredictRunning.value = true;
    trainPredictStatusMessage.value = "Starting training...";

    try {
      const trainResp = await createTrainingJobApiV1TrainingJobsPost({
        dataset_id: datasetId.value,
        trainer_id: trainerId,
      });
      const trainJob = trainResp.data as TrainingJob;
      trainPredictStatusMessage.value = `Training ${trainJob.id?.slice(0, 8)}...`;

      for (let attempt = 0; attempt < 180; attempt += 1) {
        await new Promise((r) => setTimeout(r, 2000));
        const jobResp = await getJobApiV1TrainingJobsJobIdGet(trainJob.id!);
        const job = (jobResp.data ?? {}) as Record<string, unknown>;
        const status = String(job.status ?? "").toLowerCase();

        if (status === "completed") {
          trainPredictStatusMessage.value = "Running predictions...";
          const artifactRefs = job.artifact_refs as
            | Array<{ kind: string; id?: string }>
            | undefined;
          const modelArtifact = (artifactRefs ?? []).find(
            (a) => a.kind === "model",
          );
          if (!modelArtifact?.id) {
            trainPredictStatusMessage.value = "";
            message.error("Training completed but no model artifact found");
            return;
          }

          const predJob = await runPredictions({
            model_id: modelArtifact.id,
            dataset_id: datasetId.value,
          });
          trainPredictStatusMessage.value = `Predicting ${predJob.id?.slice(0, 8)}...`;

          for (let pAttempt = 0; pAttempt < 120; pAttempt += 1) {
            await new Promise((r) => setTimeout(r, 1500));
            const pJob = await getPredictionJob(predJob.id!);
            const pStatus = String(pJob.status ?? "").toLowerCase();

            if (pStatus === "completed") {
              trainPredictStatusMessage.value = "";
              void queryClient.invalidateQueries({
                queryKey: [
                  "api",
                  "v1",
                  "datasets",
                  datasetId.value,
                  "latest-predictions",
                ],
              });
              void queryClient.invalidateQueries({
                queryKey: ["sc", "class-list", datasetId.value],
              });
              if (mounted.value) {
                message.success("Prediction done");
              }
              return;
            }
            if (pStatus === "failed" || pStatus === "cancelled") {
              trainPredictStatusMessage.value = "";
              message.error(`Prediction ${pStatus}`);
              return;
            }
          }
          trainPredictStatusMessage.value = "";
          message.warning(
            "Prediction is still running. Refresh later for results.",
          );
          return;
        }

        if (status === "failed" || status === "cancelled") {
          trainPredictStatusMessage.value = "";
          message.error(`Training ${status}`);
          return;
        }
      }
      trainPredictStatusMessage.value = "";
      message.warning("Training is still running. Check back later.");
    } catch (err: unknown) {
      trainPredictStatusMessage.value = "";
      message.error((err as Error)?.message ?? "Train & Predict failed");
    } finally {
      isTrainPredictRunning.value = false;
    }
  }

  // ── Return ─────────────────────────────────────────────────────────

  return {
    datasetId,
    dataset: selectedDataset,
    isLoading,
    isError,
    errorMessage,
    scSamples,
    isBlinkLoading,
    isMapLoading,
    samplesError,
    fetchMoreSamples,
    hasMoreSamples,
    isFetchingMoreSamples,
    plotPointTotal,
    annotatedCount,
    labelSpace,
    effectiveLabels,
    labelOptions,
    classNumberOptions,
    classList,

    activeMapTab,
    mapZoom,
    setActiveMapTab,
    setMapZoom,
    waferDisplay,
    waferFilterIds,
    mapFilterCount,
    applyMapBoxFilter,
    selectedDefectIds,
    mapSelectedDefectIds,
    selectedCount,
    selectDefectIds,
    clearSelection,
    filteredScSamples,

    waferGeometry,
    dieDisplay,
    dieFullPoints,
    dieRenderPoints,
    reticleDisplay,
    reticleXDieCount,
    reticleYDieCount,
    reticleDieSizeX,
    reticleDieSizeY,
    reticleOptions,
    updateReticleOptions,
    isReticleMapLoading: computed(() => false),
    reticleMapError,

    blinkTableData,

    annotationGridItems,
    annotationDraft,
    draftCount,
    isSubmitting: computed(() => bulkAnnotateMutation.isPending.value),
    setAnnotationDraft,
    clearDrafts,
    submitAnnotations,
    addLabel,
    addLabelError,
    isAddingLabel,

    predictionLabels,
    predictionConfidences,
    isPredictionsLoading,

    activeTab,
    inspectionContext,

    showSamplingModal,
    samplingCount,
    assignDefaultDraftLabel,
    applySampling,

    selectedTrainerId,
    trainerOptions,
    isTrainPredictRunning,
    trainPredictStatusMessage,
    trainAndPredict,
  };
}
