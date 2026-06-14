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
import { withAuthQueryParams } from "@/shared/api/client";
import { buildBlinkTableData } from "@/shared/utils/blink-table-data";
import type { BlinkSampleInput } from "@/shared/utils/blink-table-data";
import type { AnnotationGridItem } from "@/shared/types/components";

import {
  useGetDatasetApiV1DatasetsDatasetIdGet,
  useScBulkCreateAnnotationsApiV1DatasetsDatasetIdAnnotationsBulkScPost,
  type ScBulkCreateAnnotationsApiV1DatasetsDatasetIdAnnotationsBulkScPostMutationResult,
  listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet,
  useListTrainersRouteApiV1TrainersGet,
  createTrainingJobApiV1TrainingJobsPost,
  getJobApiV1TrainingJobsJobIdGet,
  getInspectionReviewImagesApiV1ScInspectionsInspectionTimeWaferKeyReviewImagesGet,
} from "@/generated/orval/endpoints/api";
import { runPredictions, getPredictionJob } from "@/shared/api/predictions";
import type { Trainer } from "@/shared/api/types";
import type { TrainingJob } from "@/generated/orval/models";
import { fetchScPlotPoints } from "../api/plotPoints";
import type { DefectList } from "../generated/proto/sc/v1/sample_pb";
import {
  DEFAULT_RETICLE_MAP_OPTIONS,
  normalizeReticleMapOptions,
  type ReticleMapOptions,
} from "./reticleMapOptions";
import { useScReclassifyStore } from "./reclassifyStore";
import type { ScDatasetInfo, ScAnnotationItem } from "../domain/models";
import type { HighlightDefect } from "../presentation/components/types";
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
  label?: string;
  predicted_label?: string;
  confidence?: number | null;
}

interface ScViewRowsPage {
  items: ScViewRow[];
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
  predictedLabel: string | null;
  confidence: number | null;
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
  classList: ComputedRef<Record<string, DefectList> | null>;

  activeMapTab: Ref<MapMode>;
  mapZoom: ComputedRef<MapViewport | null>;
  setActiveMapTab: (mode: MapMode) => void;
  setMapZoom: (viewport: MapViewport | null) => void;
  waferDisplay: ComputedRef<number[]>;
  mapFilter: Ref<Record<string, (number|string)[]>>;
  legendGroupBy: Ref<string | null>;
  activeFilterCount: ComputedRef<number>;
  handleMapFilterChange: (filter: Record<string, (number|string)[]>) => void;
  handleLegendGroupByChange: (source: string | null) => void;
  clearMapFilter: () => void;
  handleBoxSelectionChange: (ids: number[]) => void;
  mapFilteredIds: Ref<Set<string>>;
  highlightDefects: ComputedRef<HighlightDefect[]>;
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

  reviewSamples: Ref<import("@/features/sc/generated/proto/sc/v1/sample_pb").ScSampleItem[]>;
  reviewLoading: Ref<boolean>;
  reviewError: Ref<string | null>;
}

function scImageUrlForRole(row: ScViewRow, image: ScViewImage): string {
  if (image.url) {
    return withAuthQueryParams(image.url);
  }
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

  const mapFilter = ref<Record<string, (number|string)[]>>({});
  const legendGroupBy = ref<string | null>(null);
  const activeFilterCount = computed(
    () => Object.values(mapFilter.value).filter((v) => v && v.length > 0).length,
  );

  const reticleOptionsState = ref<ReticleMapOptions>({
    ...DEFAULT_RETICLE_MAP_OPTIONS,
  });
  const reticleOptions = computed<ReticleMapOptions>(() =>
    normalizeReticleMapOptions(reticleOptionsState.value),
  );

  const plotPointsQuery = useQuery({
    queryKey: computed(() => ["sc", "plot-points", datasetId.value]),
    queryFn: () =>
      fetchScPlotPoints(
        datasetId.value,
        reticleOptions.value,
        mapFilter.value,
        legendGroupBy.value ?? undefined,
      ),
    enabled: computed(() => !!selectedDataset.value),
    retry: false,
  });
  const classList = computed(() => plotPointsQuery.data.value?.legendGroups ?? null);

  // ── Selection state (Blink table box-selection, separate from filter) ─

  function handleBoxSelectionChange(ids: number[]): void {
    mapFilteredIds.value = new Set(ids.map(String));
    sampledIds.value = new Set();
  }

  const selectedDefectIds = computed(
    () => new Set(reclassifyStore.selectedDefectIdsByDataset[datasetId.value] ?? []),
  );
  const mapSelectedDefectIds = computed(
    () =>
      new Set(
        [...mapFilteredIds.value]
          .map(Number)
          .filter(Number.isFinite),
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

  // ── BlinkTable data source (decoupled from selection highlight) ───

  const mapFilteredIds = ref<Set<string>>(new Set());
  const sampledIds = ref<Set<string>>(new Set());

  const blinkSourceDefectIds = computed<string[] | null>(() => {
    if (sampledIds.value.size > 0) return [...sampledIds.value];
    if (mapFilteredIds.value.size > 0) return [...mapFilteredIds.value];
    return null;
  });

  const sampleRowsInfiniteQuery = useInfiniteQuery({
    queryKey: computed(() => [
      "sc",
      "view-samples-paged",
      datasetId.value,
      blinkSourceDefectIds.value
        ? blinkSourceDefectIds.value.join(",")
        : null,
    ]),
    initialPageParam: 0,
    queryFn: async ({ pageParam }: { pageParam: number }) => {
      const sourceIds = blinkSourceDefectIds.value;
      if (sourceIds) {
        const ids = sourceIds.slice(pageParam, pageParam + pageSize);
        const resp =
          await listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet(
            datasetId.value,
            "patch_image_v1",
            { sampleIds: ids.join(","), limit: ids.length },
          );
        return (resp.data ?? { items: [], total: sourceIds.length }) as ScViewRowsPage;
      }
      const resp =
        await listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet(
          datasetId.value,
          "patch_image_v1",
          { offset: pageParam, limit: pageSize },
        );
      return (resp.data ?? { items: [], total: 0 }) as ScViewRowsPage;
    },
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((n, p) => n + p.items.length, 0);
      const sourceIds = blinkSourceDefectIds.value;
      if (sourceIds) return loaded < sourceIds.length ? loaded : undefined;
      return loaded < lastPage.total ? loaded : undefined;
    },
    enabled: computed(() => !!selectedDataset.value),
    retry: false,
  });

  // ── Annotation join ────────────────────────────────────────────────

  const loadedRows = computed<ScViewRow[]>(() => {
    return (
      sampleRowsInfiniteQuery.data.value?.pages ?? []
    ).flatMap((page) => page.items);
  });

  const scSamples = computed<ReclassifySample[]>(() => {
    const rows = loadedRows.value;
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
      currentLabel: r.label || null,
      predictedLabel: r.predicted_label || null,
      confidence: r.confidence ?? null,
    }));
  });

  // ── Highlight defects from selectedDefectIds (BlinkTable selection) ──

  const sampleCoordsByDefectId = computed(() => {
    const map = new Map<string, ReclassifySample>();
    for (const s of scSamples.value) map.set(s.defectId, s);
    return map;
  });

  const highlightDefects = computed<HighlightDefect[]>(() => {
    const coords = sampleCoordsByDefectId.value;
    const result: HighlightDefect[] = [];
    for (const id of selectedDefectIds.value) {
      const s = coords.get(id);
      if (!s) continue;
      result.push({
        defectId: Number(id),
        waferX: s.waferX,
        waferY: s.waferY,
        dieX: s.dieX,
        dieY: s.dieY,
        reticleX: 0,
        reticleY: 0,
      });
    }
    return result;
  });

  const isBlinkLoading = computed(
    () => sampleRowsInfiniteQuery.isLoading.value,
  );

  const isMapLoading = computed(
    () => plotPointsQuery.isLoading.value,
  );
  const samplesError = computed<string | null>(
    () =>
      (plotPointsQuery.error.value as Error)?.message ??
      (sampleRowsInfiniteQuery.error.value as Error)?.message ??
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

  const annotatedCount = computed<number>(() => {
    if (legendGroupBy.value === "annotation") {
      return Object.values(classList.value ?? {}).reduce(
        (count, group) => count + group.count, 0,
      );
    }
    return scSamples.value.filter((s) => s.currentLabel).length;
  });

  async function fetchMoreSamples(): Promise<unknown> {
    if (
      sampleRowsInfiniteQuery.isFetching.value ||
      sampleRowsInfiniteQuery.isFetchingNextPage.value
    )
      return undefined;

    if (sampleRowsInfiniteQuery.hasNextPage.value) {
      return sampleRowsInfiniteQuery.fetchNextPage();
    }
    return undefined;
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
    const values = legendGroupBy.value === "bin"
      ? Object.keys(classList.value ?? {})
      : [];
    if (values.length > 0) return values.sort((a, b) => Number(a) - Number(b));
    return packedPointOptions(plotPointsQuery.data.value?.waferPoints ?? [], 4);
  });

  const labelOptions = computed(() => {
    if (labelSpace.value.length > 0) return labelSpace.value;
    return roughBinOptions.value;
  });

  const classNumberOptions = computed(() => {
    const values = legendGroupBy.value === "class"
      ? Object.keys(classList.value ?? {}).sort((a, b) => Number(a) - Number(b))
      : [];
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
    if (legendGroupBy.value === "prediction") {
      for (const [label, group] of Object.entries(classList.value ?? {})) {
        if (label === "__unlabeled__") continue;
        for (const defectId of group.defectIds) {
          map[String(defectId)] = label;
        }
      }
      if (Object.keys(map).length > 0) return map;
    }
    for (const s of scSamples.value) {
      if (s.predictedLabel) map[s.defectId] = s.predictedLabel;
    }
    return map;
  });

  const predictionConfidences = computed<Record<string, number | null>>(() => {
    const map: Record<string, number | null> = {};
    for (const s of scSamples.value) {
      map[s.defectId] = s.confidence;
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

  // ── Map filter + selection state ─────────────────────────────────────

  const filteredScSamples = computed<ReclassifySample[]>(() => scSamples.value);

  function handleMapFilterChange(filter: Record<string, (number|string)[]>): void {
    mapFilter.value = filter;
    void plotPointsQuery.refetch();
  }

  function handleLegendGroupByChange(source: string | null): void {
    legendGroupBy.value = source;
    void plotPointsQuery.refetch();
  }

  function clearMapFilter(): void {
    mapFilter.value = {};
    mapFilteredIds.value = new Set();
    sampledIds.value = new Set();
    void plotPointsQuery.refetch();
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

    let resp;
    if (mapFilteredIds.value.size > 0) {
      const pool = [...mapFilteredIds.value];
      const shuffled = pool.sort(() => Math.random() - 0.5);
      const picked = shuffled.slice(0, count);
      resp =
        await listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet(
          datasetId.value,
          "patch_image_v1",
          { sampleIds: picked.join(","), limit: picked.length },
        );
    } else {
      resp =
        await listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet(
          datasetId.value,
          "patch_image_v1",
          { order_by: "random", limit: count },
        );
    }
    const data = (resp.data ?? { items: [], total: 0 }) as ScViewRowsPage;
    const sampled = data.items.map((row) => String(row.defect_id));
    if (sampled.length === 0) return;

    sampledIds.value = new Set(sampled);

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
              await Promise.all([
                queryClient.refetchQueries({
                  queryKey: [
                    "api",
                    "v1",
                    "datasets",
                    datasetId.value,
                    "latest-predictions",
                  ],
                }),
                queryClient.refetchQueries({
                  queryKey: ["sc", "class-list", datasetId.value],
                }),
                queryClient.refetchQueries({
                  queryKey: [
                    "sc",
                    "view-annotations-paged",
                    datasetId.value,
                  ],
                }),
              ]);
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

  // ── Review images (fetched via /sc/inspections/.../review-images) ──

  const reviewSamples = ref<import("@/features/sc/generated/proto/sc/v1/sample_pb").ScSampleItem[]>([]);
  const reviewLoading = ref(false);
  const reviewError = ref<string | null>(null);

  async function fetchReviewImages(): Promise<void> {
    const ctx = inspectionContext.value;
    if (!ctx || !ctx.inspectionTime || !ctx.waferKey) {
      reviewSamples.value = [];
      reviewLoading.value = false;
      reviewError.value = null;
      return;
    }
    reviewLoading.value = true;
    reviewError.value = null;
    try {
      const data = await getInspectionReviewImagesApiV1ScInspectionsInspectionTimeWaferKeyReviewImagesGet(
        ctx.inspectionTime,
        Number(ctx.waferKey),
      );
      const { create } = await import("@bufbuild/protobuf");
      const { ScSampleItemSchema, ReviewImageSchema } = await import(
        "@/features/sc/generated/proto/sc/v1/sample_pb"
      );
      const inspTimeBigInt = BigInt(Date.parse(ctx.inspectionTime)) * BigInt(1_000_000);
      const resp = data.data;
      if (!("items" in resp)) {
        throw new Error("Failed to load review images");
      }
      reviewSamples.value = resp.items.map(
        (item: { defect_id: string; review_images: Array<{ image_name: string; image_id: number; image_type: string }> }) =>
          create(ScSampleItemSchema, {
            defectId: Number(item.defect_id),
            inspectionTime: inspTimeBigInt,
            waferKey: Number(ctx.waferKey),
            reviewImages: item.review_images.map(
              (image: { image_name: string; image_id: number; image_type: string }) =>
                create(ReviewImageSchema, {
                  imageName: image.image_name,
                  imageId: image.image_id,
                  imageType: image.image_type,
                })
            ),
          })
      );
    } catch (err: unknown) {
      reviewError.value = (err as Error)?.message ?? "Failed to load review images";
      reviewSamples.value = [];
    } finally {
      reviewLoading.value = false;
    }
  }

  watch(
    () => [inspectionContext.value?.inspectionTime, inspectionContext.value?.waferKey],
    () => { fetchReviewImages(); },
    { immediate: true },
  );

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
    mapFilter,
    legendGroupBy,
    activeFilterCount,
    handleMapFilterChange,
    handleLegendGroupByChange,
    clearMapFilter,
    handleBoxSelectionChange,
    mapFilteredIds,
    highlightDefects,
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
    reviewSamples,
    reviewLoading,
    reviewError,
  };
}
