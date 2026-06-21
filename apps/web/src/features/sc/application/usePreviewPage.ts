import {
  computed,
  onMounted,
  ref,
  watch,
  type ComputedRef,
  type Ref,
} from "vue";
import { useRoute } from "vue-router";
import { useMessage } from "naive-ui";
import type { DataTableColumns } from "naive-ui";
import {
  useGetInspectionsApiV1ScInspectionsGet,
  getInspectionReviewImagesApiV1ScInspectionsInspectionTimeWaferKeyReviewImagesGet,
} from "@/generated/orval/endpoints/api";
import { streamApiSse } from "@/shared/api/sse";
import { create } from "@bufbuild/protobuf";
import {
  type DefectList,
  ReviewImageSchema,
  ScSampleItemSchema,
} from "../generated/proto/sc/v1/sample_pb";
import {
  fetchScInspectionMapPoints,
  warmupScInspectionMapPoints,
  type ScMapFilter,
} from "../api/plotPoints";
import { defaultDefectIds, fetchInspectionDefectIds } from "../api/defectIds";
import type { ScSampleItem } from "../generated/proto/sc/v1/sample_pb";
import type {
  InspectionSummaryItem,
  ScImportProgressEvent,
  ScImportPayload,
  ScImportResponse,
} from "../domain/models";
import type { GetInspectionsApiV1ScInspectionsGetParams } from "@/generated/orval/models/getInspectionsApiV1ScInspectionsGetParams";
import type {
  ScSampleTableFilter,
  ScSampleTableSort,
} from "../domain/sampleTable";
import {
  DEFAULT_RETICLE_MAP_OPTIONS,
  normalizeReticleMapOptions,
  type ReticleMapOptions,
} from "./reticleMapOptions";

// ── Tab type ──────────────────────────────────────────────────────────

export interface PreviewTab {
  id: string;
  type: "summary" | "inspection";
  label: string;
  pinned?: boolean;
  inspectionTime?: string;
  waferKey?: number;
  inspectionItem?: InspectionSummaryItem;
  /** Deprecated: legacy full protobuf sample payload; kept for compatibility shims. */
  samples: ScSampleItem[];
  /** Deprecated: use inspectionItem.defects for patch count. */
  samplesTotal: number;
  samplesLoading: boolean;
  samplesError: string | null;
  patchSamples: ScSampleItem[];
  reviewSamples: ScSampleItem[];
  reviewLoading: boolean;
  reviewError: string | null;
  mapLoading: boolean;
  mapError: string | null;
  mapStreamMessage: string;
  mapProgressPercent: number;
  activeMapTab: "wafer" | "die" | "reticle";
  /** Wafer geometry from the inspection / dataset (center, origin, die sizes) */
  waferGeometry: {
    waferRadiusNm: number;
    centerX: number;
    centerY: number;
    originX: number;
    originY: number;
    dieSizeX: number;
    dieSizeY: number;
  } | null;
  /** Pre-computed wafer display flat array [x, y, defect_id, class_num, rough_bin, has_review, ...] — 6 ints per point */
  waferDisplay: number[];
  /** Pre-computed die display flat array [dieX, dieY, defect_id, class_num, rough_bin, has_review, ...] — 6 ints per point */
  dieDisplay: number[];
  /** Pre-computed reticle display flat array [reticleX, reticleY, id, ...] from backend */
  reticleDisplay: number[];
  /** Unzoomed display arrays — backup of the full display before zooming, restored on zoom-out / map-tab switch */
  unzoomedWaferDisplay: number[];
  unzoomedDieDisplay: number[];
  unzoomedReticleDisplay: number[];
  legendGroups: Record<string, DefectList> | null;
  reticleXDieCount: number;
  reticleYDieCount: number;
  reticleDieSizeX: number;
  reticleDieSizeY: number;
  reticleOptions: ReticleMapOptions;
  zoom: { x: number; y: number; w: number; h: number } | null;
  selectedDefectIds: number[];
  tableFilter: ScSampleTableFilter;
  tableSort: ScSampleTableSort | null;
  legendGroupBy: string | null;
}

type MapMode = "wafer" | "die" | "reticle";

// ── Composable result type ────────────────────────────────────────────

export interface PreviewPageState {
  datasetId: Ref<string>;
  dateRange: Ref<[number, number] | null>;
  lotIdFilter: Ref<string>;
  eqpIdFilter: Ref<string>;
  layerIdFilter: Ref<string>;
  deviceFilter: Ref<string>;
  classifyHref: ComputedRef<string>;

  summaries: Ref<InspectionSummaryItem[]>;
  summariesLoading: Ref<boolean>;
  summariesError: Ref<string | null>;
  summariesEmpty: Ref<boolean>;
  inspectionColumns: ComputedRef<DataTableColumns<InspectionSummaryItem>>;

  tabs: Ref<PreviewTab[]>;
  activeTabId: Ref<string | null>;
  activeTab: ComputedRef<PreviewTab | null>;

  searchInspections: () => Promise<void>;
  createSummaryTab: () => void;
  openInspectionTab: (row: InspectionSummaryItem) => void;
  closeTab: (id: string) => void;
  fetchSamplesForTab: (tab: PreviewTab) => Promise<void>;
  fetchPreviewDataForTab: (tab: PreviewTab) => Promise<void>;
  setMapTab: (tabId: string, value: "wafer" | "die" | "reticle") => void;
  setZoom: (
    tabId: string,
    vp: { x: number; y: number; w: number; h: number } | null,
  ) => Promise<void>;
  updateReticleOptions: (
    tabId: string,
    options: ReticleMapOptions,
  ) => Promise<void>;
  setSelectedDefectIds: (tabId: string, ids: number[]) => void;
  handleTableFilterChange: (tabId: string, filter: ScSampleTableFilter) => void;
  handleTableSortChange: (
    tabId: string,
    sort: { field: string; direction: "asc" | "desc" | null },
  ) => void;
  handleLegendGroupByChange: (tabId: string, groupBy: string | null) => void;
  rowKey: (row: InspectionSummaryItem) => string;
  rowProps: (row: InspectionSummaryItem) => Record<string, unknown>;

  showImportModal: Ref<boolean>;
  importSourceInspectionTime: Ref<string>;
  importSourceWaferKey: Ref<number>;
  importDatasetName: Ref<string>;
  importStorageMode: Ref<"file_shard_sparse">;
  isImporting: Ref<boolean>;
  importProgress: Ref<ScImportProgressEvent>;
  importError: Ref<string>;
  storageModeOptions: { label: string; value: string }[];
  handleImport: () => Promise<void>;
  openImportForInspection: (item: InspectionSummaryItem) => void;
  startImportDirectly: (item: InspectionSummaryItem) => void;
}

// ── Composable ────────────────────────────────────────────────────────

export function usePreviewPage(): PreviewPageState {
  const route = useRoute();
  const message = useMessage();

  // ── Route ────────────────────────────────────────

  const classifyHref = computed(() => {
    if (!datasetId.value.trim()) return "#";
    let url = `/datasets/${datasetId.value.trim()}/sc/classify`;
    const tab = activeTab.value;
    if (tab?.type === "inspection" && tab.inspectionTime) {
      url += `?inspectionTime=${encodeURIComponent(tab.inspectionTime)}&waferKey=${tab.waferKey ?? ""}`;
    }
    return url;
  });

  // ── Search inputs ────────────────────────────────

  const datasetId = ref((route.query.datasetId as string) ?? "");

  function getDefaultDateRange(): [number, number] {
    const now = new Date();
    const today = Date.UTC(
      now.getUTCFullYear(),
      now.getUTCMonth(),
      now.getUTCDate(),
    );
    const startTime = today - 3 * 24 * 60 * 60 * 1000;
    const tomorrow = today + 24 * 60 * 60 * 1000;
    return [startTime, tomorrow];
  }

  const dateRange = ref<[number, number] | null>(getDefaultDateRange());

  const lotIdFilter = ref("");
  const eqpIdFilter = ref("");
  const layerIdFilter = ref("");
  const deviceFilter = ref("");

  // ── Inspection summaries (JSON, snake_case) ─────

  const summaries = ref<InspectionSummaryItem[]>([]);
  const summariesLoading = ref(false);
  const summariesError = ref<string | null>(null);
  const summariesEmpty = ref(false);

  const searchParams = ref<GetInspectionsApiV1ScInspectionsGetParams | null>(
    null,
  );

  const searchNonce = ref(0);

  const inspectionsQuery = useGetInspectionsApiV1ScInspectionsGet(
    computed(() => searchParams.value ?? { start_time: "", end_time: "" }),
    {
      query: {
        enabled: computed(() => searchParams.value !== null),
        staleTime: 0,
        queryKey: computed(
          () =>
            [
              "api",
              "v1",
              "sc",
              "inspections",
              searchNonce.value,
              searchParams.value ?? { start_time: "", end_time: "" },
            ] as const,
        ),
      },
    },
  );

  type SummaryFilterKey =
    | "inspection_time"
    | "lot_id"
    | "wafer_id"
    | "layer_id"
    | "device";

  function summaryFilterOptions(key: SummaryFilterKey) {
    const values = new Set<string>();
    for (const row of summaries.value) {
      const value = row[key];
      if (value !== undefined && value !== null && String(value).length > 0) {
        values.add(String(value));
      }
    }
    return [...values]
      .sort((left, right) =>
        left.localeCompare(right, undefined, { numeric: true }),
      )
      .map((value) => ({ label: value, value }));
  }

  function summaryStringSorter(
    key: SummaryFilterKey,
  ): (left: InspectionSummaryItem, right: InspectionSummaryItem) => number {
    return (left, right) =>
      String(left[key] ?? "").localeCompare(
        String(right[key] ?? ""),
        undefined,
        {
          numeric: true,
        },
      );
  }

  function summaryStringFilter(
    key: SummaryFilterKey,
  ): (value: string | number, row: InspectionSummaryItem) => boolean {
    return (value, row) => String(row[key] ?? "") === String(value);
  }

  const inspectionColumns = computed<DataTableColumns<InspectionSummaryItem>>(
    () => [
      {
        key: "inspection_time",
        title: "Inspection Time",
        width: 200,
        ellipsis: { tooltip: true },
        sorter: (left, right) =>
          Date.parse(left.inspection_time) - Date.parse(right.inspection_time),
        filter: summaryStringFilter("inspection_time"),
        filterOptions: summaryFilterOptions("inspection_time"),
        filterMultiple: true,
      },
      {
        key: "lot_id",
        title: "Lot ID",
        width: 100,
        sorter: summaryStringSorter("lot_id"),
        filter: summaryStringFilter("lot_id"),
        filterOptions: summaryFilterOptions("lot_id"),
        filterMultiple: true,
      },
      {
        key: "wafer_id",
        title: "Wafer ID",
        width: 80,
        sorter: summaryStringSorter("wafer_id"),
        filter: summaryStringFilter("wafer_id"),
        filterOptions: summaryFilterOptions("wafer_id"),
        filterMultiple: true,
      },
      {
        key: "layer_id",
        title: "Layer ID",
        width: 80,
        sorter: summaryStringSorter("layer_id"),
        filter: summaryStringFilter("layer_id"),
        filterOptions: summaryFilterOptions("layer_id"),
        filterMultiple: true,
      },
      {
        key: "device",
        title: "Device",
        width: 90,
        sorter: summaryStringSorter("device"),
        filter: summaryStringFilter("device"),
        filterOptions: summaryFilterOptions("device"),
        filterMultiple: true,
      },
      { key: "defects", title: "Defects", width: 80 },
      {
        key: "images",
        title: "Images",
        width: 120,
        ellipsis: { tooltip: true },
      },
      { key: "eqp_id", title: "Equipment ID", width: 80 },
      { key: "recipe_id", title: "Recipe ID", width: 80 },
    ],
  );

  // ── Tab system ───────────────────────────────────

  const tabs = ref<PreviewTab[]>([]);
  const activeTabId = ref<string | null>(null);
  const activeTab = computed(
    () => tabs.value.find((t) => t.id === activeTabId.value) ?? null,
  );

  let nextTabId = 1;

  function createSummaryTab(): void {
    const existing = tabs.value.find((tab) => tab.type === "summary");
    if (existing) {
      activeTabId.value = existing.id;
      return;
    }

    const id = `tab-${nextTabId++}`;
    tabs.value.unshift({
      id,
      type: "summary",
      label: "Summary",
      pinned: true,
      samples: [],
      samplesTotal: 0,
      samplesLoading: false,
      samplesError: null,
      patchSamples: [],
      reviewSamples: [],
      reviewLoading: false,
      reviewError: null,
      mapLoading: false,
      mapError: null,
      mapStreamMessage: "",
      mapProgressPercent: 0,
      activeMapTab: "wafer",
      waferGeometry: null,
      waferDisplay: [],
      dieDisplay: [],
      reticleDisplay: [],
      unzoomedWaferDisplay: [],
      unzoomedDieDisplay: [],
      unzoomedReticleDisplay: [],
      legendGroups: null,
      reticleXDieCount: 10,
      reticleYDieCount: 10,
      reticleDieSizeX: 100000,
      reticleDieSizeY: 100000,
      reticleOptions: { ...DEFAULT_RETICLE_MAP_OPTIONS },
      zoom: null,
      selectedDefectIds: [],
      tableFilter: {},
      tableSort: null,
      legendGroupBy: null,
    });
    activeTabId.value = id;
  }

  function openInspectionTab(row: InspectionSummaryItem): void {
    const id = `tab-${nextTabId++}`;
    const label = row.lot_id
      ? `${row.lot_id} / W${row.wafer_key}`
      : `W${row.wafer_key}`;
    const reticleOptions = normalizeReticleMapOptions(
      DEFAULT_RETICLE_MAP_OPTIONS,
    );
    const tab: PreviewTab = {
      id,
      type: "inspection",
      label,
      inspectionTime: row.inspection_time,
      waferKey: row.wafer_key,
      inspectionItem: row,
      samples: [],
      samplesTotal: row.defects,
      samplesLoading: false,
      samplesError: null,
      patchSamples: makePatchSamples(row),
      reviewSamples: [],
      reviewLoading: true,
      reviewError: null,
      mapLoading: true,
      mapError: null,
      mapStreamMessage: "Loading 0%",
      mapProgressPercent: 0,
      activeMapTab: "wafer",
      waferGeometry: {
        waferRadiusNm: 150_000_000,
        centerX: row.center_x ?? 0,
        centerY: row.center_y ?? 0,
        originX: row.origin_x ?? 0,
        originY: row.origin_y ?? 0,
        dieSizeX: row.die_size_x ?? 24000,
        dieSizeY: row.die_size_y ?? 24000,
      },
      waferDisplay: [],
      dieDisplay: [],
      reticleDisplay: [],
      unzoomedWaferDisplay: [],
      unzoomedDieDisplay: [],
      unzoomedReticleDisplay: [],
      legendGroups: null,
      reticleXDieCount: reticleOptions.xDieCount,
      reticleYDieCount: reticleOptions.yDieCount,
      reticleDieSizeX: row.die_size_x || 100000,
      reticleDieSizeY: row.die_size_y || 100000,
      reticleOptions,
      zoom: null,
      selectedDefectIds: [],
      tableFilter: {},
      tableSort: null,
      legendGroupBy: null,
    };
    tabs.value.push(tab);
    activeTabId.value = id;
    void fetchPreviewDataForTab(tab);
  }

  function inspectionTimeEpochSeconds(value: string): bigint {
    const parsed = Date.parse(value);
    if (!Number.isFinite(parsed)) return 0n;
    return BigInt(Math.floor(parsed / 1000));
  }

  function makePatchSamples(row: InspectionSummaryItem): ScSampleItem[] {
    const defectIds = defaultDefectIds(row.defects ?? 0);
    return makePatchSamplesForDefectIds(row, defectIds);
  }

  function makePatchSamplesForDefectIds(
    row: InspectionSummaryItem,
    defectIds: number[],
  ): ScSampleItem[] {
    const inspectionTime = inspectionTimeEpochSeconds(row.inspection_time);
    return defectIds.map((defectId) =>
      create(ScSampleItemSchema, {
        defectId,
        inspectionTime,
        waferKey: row.wafer_key,
        reviewImages: [],
      }),
    );
  }

  async function fetchPreviewDataForTab(tab: PreviewTab): Promise<void> {
    await Promise.allSettled([
      fetchDefectIdsForTab(tab),
      fetchMapPointsForTab(tab),
      fetchReviewImagesForTab(tab),
    ]);
  }

  async function fetchDefectIdsForTab(tab: PreviewTab): Promise<void> {
    const tabId = tab.id;
    if (
      !tab.inspectionTime ||
      tab.waferKey === undefined ||
      !tab.inspectionItem
    )
      return;
    try {
      const defectIds = await fetchInspectionDefectIds(
        tab.inspectionTime,
        tab.waferKey,
      );
      const idx = tabs.value.findIndex((t) => t.id === tabId);
      if (idx === -1 || tabs.value[idx].type !== "inspection") return;
      tabs.value[idx] = {
        ...tabs.value[idx],
        samplesTotal: defectIds.length,
        patchSamples: makePatchSamplesForDefectIds(
          tab.inspectionItem,
          defectIds,
        ),
      };
    } catch {
      // Keep the immediate 1..summary.defects fallback if the optional id list fails.
    }
  }

  async function fetchMapPointsForTab(
    tab: PreviewTab,
    modes: MapMode[] = ["wafer", "die", "reticle"],
  ): Promise<void> {
    const tabId = tab.id;
    if (!tab.inspectionTime || tab.waferKey === undefined) return;
    const idx = tabs.value.findIndex((t) => t.id === tabId);
    if (idx === -1) return;
    tabs.value[idx] = {
      ...tabs.value[idx],
      mapLoading: true,
      mapError: null,
      mapStreamMessage: "Loading 0%",
      mapProgressPercent: 0,
    };

    const opts = normalizeReticleMapOptions(tab.reticleOptions);
    try {
      const allThree = modes.length === 3;
      const results: {
        mode: MapMode;
        result: Awaited<ReturnType<typeof _fetchMapData>>;
      }[] = [];

      if (allThree && !tab.zoom) {
        const combined = await _fetchMapData(
          tab,
          undefined,
          opts,
          undefined,
          tab.legendGroupBy ?? undefined,
        );
        results.push(
          { mode: "wafer", result: combined },
          { mode: "die", result: combined },
          { mode: "reticle", result: combined },
        );
      } else {
        const perMode = await Promise.all(
          modes.map(async (mode) => ({
            mode,
            result: await _fetchMapData(
              tab,
              mode,
              opts,
              undefined,
              tab.legendGroupBy ?? undefined,
            ),
          })),
        );
        results.push(...perMode);
      }

      const idx2 = tabs.value.findIndex((t) => t.id === tabId);
      if (idx2 === -1) return;

      const current = tabs.value[idx2];
      const firstResult = results[0]?.result;
      const geo = firstResult?.geometry;
      const baseUpdate: Partial<PreviewTab> = {
        mapLoading: false,
        mapStreamMessage: "",
        mapProgressPercent: 100,
        waferGeometry: geo
          ? {
              waferRadiusNm: geo.waferRadiusNm,
              centerX: geo.centerX,
              centerY: geo.centerY,
              originX: geo.originX,
              originY: geo.originY,
              dieSizeX: geo.dieSizeX,
              dieSizeY: geo.dieSizeY,
            }
          : tabs.value[idx2].waferGeometry,
        reticleXDieCount: firstResult?.reticleXDieCount || opts.xDieCount,
        reticleYDieCount: firstResult?.reticleYDieCount || opts.yDieCount,
        reticleDieSizeX: geo?.dieSizeX ?? tabs.value[idx2].reticleDieSizeX,
        reticleDieSizeY: geo?.dieSizeY ?? tabs.value[idx2].reticleDieSizeY,
        reticleOptions: {
          xDieCount: firstResult?.reticleXDieCount || opts.xDieCount,
          yDieCount: firstResult?.reticleYDieCount || opts.yDieCount,
          xDieShift: opts.xDieShift,
          yDieShift: opts.yDieShift,
        },
        legendGroups:
          (firstResult?.legendGroupBy || "class") ===
          (tab.legendGroupBy ?? "class")
            ? (firstResult?.legendGroups ?? null)
            : null,
      };
      for (const { mode, result } of results) {
        if (mode === "wafer") baseUpdate.waferDisplay = result.waferPoints;
        if (mode === "die") baseUpdate.dieDisplay = result.diePoints;
        if (mode === "reticle")
          baseUpdate.reticleDisplay = result.reticlePoints;
      }
      tabs.value[idx2] = {
        ...current,
        ...baseUpdate,
        unzoomedWaferDisplay: current.zoom
          ? current.unzoomedWaferDisplay
          : (baseUpdate.waferDisplay ?? current.unzoomedWaferDisplay),
        unzoomedDieDisplay: current.zoom
          ? current.unzoomedDieDisplay
          : (baseUpdate.dieDisplay ?? current.unzoomedDieDisplay),
        unzoomedReticleDisplay: current.zoom
          ? current.unzoomedReticleDisplay
          : (baseUpdate.reticleDisplay ?? current.unzoomedReticleDisplay),
      };
    } catch (err) {
      const idx2 = tabs.value.findIndex((t) => t.id === tabId);
      if (idx2 !== -1) {
        tabs.value[idx2] = {
          ...tabs.value[idx2],
          mapLoading: false,
          mapStreamMessage: "",
          mapProgressPercent: 0,
          mapError:
            err instanceof Error ? err.message : "Failed to fetch map points",
        };
      }
    }
  }

  async function _fetchMapData(
    tab: PreviewTab,
    mode: MapMode | undefined,
    opts: ReturnType<typeof normalizeReticleMapOptions>,
    filter?: ScMapFilter,
    legendGroupBy?: string,
  ) {
    const inspectionTime = tab.inspectionTime;
    const waferKey = tab.waferKey;
    if (!inspectionTime || waferKey === undefined) {
      throw new Error("Missing inspectionTime or waferKey on tab");
    }
    const updateProgress = (
      status: "warmup" | "headers" | "bytes" | "decode",
      loaded: number,
      _message?: string,
      total?: number,
    ) => {
      const idx = tabs.value.findIndex((t) => t.id === tab.id);
      if (idx === -1) return;
      const boundedTotal = total && total > 0 ? total : 0;
      const percent =
        status === "decode"
          ? 100
          : boundedTotal > 0
            ? Math.max(
                0,
                Math.min(99, Math.round((loaded / boundedTotal) * 100)),
              )
            : 0;
      const label = status === "warmup" ? "Loading" : "Streaming";
      tabs.value[idx] = {
        ...tabs.value[idx],
        mapStreamMessage: `${label} ${percent}%`,
        mapProgressPercent: percent,
      };
    };
    await warmupScInspectionMapPoints(
      inspectionTime,
      waferKey,
      opts,
      filter,
      legendGroupBy,
      mode ? { mode, zoom: tab.zoom } : { zoom: tab.zoom },
      updateProgress,
    );
    return fetchScInspectionMapPoints(
      inspectionTime,
      waferKey,
      opts,
      filter,
      legendGroupBy,
      mode ? { mode, zoom: tab.zoom } : { zoom: tab.zoom },
      updateProgress,
    );
  }

  async function fetchReviewImagesForTab(tab: PreviewTab): Promise<void> {
    const tabId = tab.id;
    if (!tab.inspectionTime || tab.waferKey === undefined) return;
    const idx = tabs.value.findIndex((t) => t.id === tabId);
    if (idx === -1) return;
    tabs.value[idx] = {
      ...tabs.value[idx],
      reviewLoading: true,
      reviewError: null,
    };
    try {
      const { data } =
        await getInspectionReviewImagesApiV1ScInspectionsInspectionTimeWaferKeyReviewImagesGet(
          tab.inspectionTime,
          tab.waferKey,
        );
      if (!data || !("items" in data))
        throw new Error("Invalid review images response");
      const inspectionTime = inspectionTimeEpochSeconds(tab.inspectionTime);
      const reviewSamples = data.items.map((item) =>
        create(ScSampleItemSchema, {
          defectId: Number(item.defect_id),
          inspectionTime,
          waferKey: tab.waferKey,
          reviewImages: item.review_images.map((image) =>
            create(ReviewImageSchema, {
              imageName: image.image_name,
              imageId: image.image_id,
              imageType: image.image_type,
            }),
          ),
        }),
      );
      const idx2 = tabs.value.findIndex((t) => t.id === tabId);
      if (idx2 !== -1) {
        tabs.value[idx2] = {
          ...tabs.value[idx2],
          reviewSamples,
          reviewLoading: false,
        };
      }
    } catch (err) {
      const idx2 = tabs.value.findIndex((t) => t.id === tabId);
      if (idx2 !== -1) {
        tabs.value[idx2] = {
          ...tabs.value[idx2],
          reviewSamples: [],
          reviewLoading: false,
          reviewError:
            err instanceof Error
              ? err.message
              : "Failed to fetch review images",
        };
      }
    }
  }

  /** @deprecated Use fetchPreviewDataForTab. */
  async function fetchSamplesForTab(tab: PreviewTab): Promise<void> {
    await fetchPreviewDataForTab(tab);
  }

  function closeTab(id: string): void {
    const idx = tabs.value.findIndex((t) => t.id === id);
    if (idx === -1) return;
    if (tabs.value[idx].pinned) {
      activeTabId.value = id;
      return;
    }
    tabs.value.splice(idx, 1);
    if (activeTabId.value === id) {
      activeTabId.value =
        tabs.value.length > 0
          ? tabs.value[Math.min(idx, tabs.value.length - 1)].id
          : null;
    }
  }

  function setMapTab(tabId: string, value: "wafer" | "die" | "reticle"): void {
    const idx = tabs.value.findIndex((t) => t.id === tabId);
    if (idx !== -1) {
      const tab = tabs.value[idx];
      tabs.value[idx] = {
        ...tab,
        activeMapTab: value,
        zoom: null,
        waferDisplay: tab.unzoomedWaferDisplay,
        dieDisplay: tab.unzoomedDieDisplay,
        reticleDisplay: tab.unzoomedReticleDisplay,
      };
    }
  }

  async function setZoom(
    tabId: string,
    vp: { x: number; y: number; w: number; h: number } | null,
  ): Promise<void> {
    const idx = tabs.value.findIndex((t) => t.id === tabId);
    if (idx === -1) return;
    const tab = tabs.value[idx];
    if (vp === null) {
      tabs.value[idx] = {
        ...tab,
        zoom: null,
        mapLoading: false,
        mapError: null,
        mapStreamMessage: "",
        mapProgressPercent: 0,
        waferDisplay: tab.unzoomedWaferDisplay,
        dieDisplay: tab.unzoomedDieDisplay,
        reticleDisplay: tab.unzoomedReticleDisplay,
      };
      return;
    }
    tabs.value[idx] = {
      ...tab,
      zoom: vp,
      mapLoading: true,
      mapError: null,
      mapStreamMessage: "Streaming 0%",
      mapProgressPercent: 0,
    };
    await fetchMapPointsForTab(tabs.value[idx], [tab.activeMapTab]);
  }

  async function updateReticleOptions(
    tabId: string,
    options: ReticleMapOptions,
  ): Promise<void> {
    const idx = tabs.value.findIndex((t) => t.id === tabId);
    if (idx === -1) return;
    const normalized = normalizeReticleMapOptions(options);
    tabs.value[idx] = {
      ...tabs.value[idx],
      reticleOptions: normalized,
      reticleXDieCount: normalized.xDieCount,
      reticleYDieCount: normalized.yDieCount,
      reticleDisplay: [],
      unzoomedReticleDisplay: [],
      mapError: null,
      mapStreamMessage: "Streaming 0%",
      mapProgressPercent: 0,
    };
    await fetchMapPointsForTab(tabs.value[idx], ["reticle"]);
  }

  function setSelectedDefectIds(tabId: string, ids: number[]): void {
    const idx = tabs.value.findIndex((t) => t.id === tabId);
    if (idx === -1) return;
    tabs.value[idx] = {
      ...tabs.value[idx],
      selectedDefectIds: ids,
    };
  }

  function handleTableFilterChange(
    tabId: string,
    filter: ScSampleTableFilter,
  ): void {
    const idx = tabs.value.findIndex((t) => t.id === tabId);
    if (idx === -1) return;
    tabs.value[idx] = {
      ...tabs.value[idx],
      tableFilter: filter,
    };
  }

  function handleTableSortChange(
    tabId: string,
    sort: { field: string; direction: "asc" | "desc" | null },
  ): void {
    const idx = tabs.value.findIndex((t) => t.id === tabId);
    if (idx === -1) return;
    tabs.value[idx] = {
      ...tabs.value[idx],
      tableSort: sort.direction
        ? { field: sort.field, direction: sort.direction }
        : null,
    };
  }

  function handleLegendGroupByChange(
    tabId: string,
    groupBy: string | null,
  ): void {
    const idx = tabs.value.findIndex((t) => t.id === tabId);
    if (idx === -1) return;
    tabs.value[idx] = {
      ...tabs.value[idx],
      legendGroupBy: groupBy,
      legendGroups: null,
      zoom: null,
      waferDisplay: tabs.value[idx].unzoomedWaferDisplay,
      dieDisplay: tabs.value[idx].unzoomedDieDisplay,
      reticleDisplay: tabs.value[idx].unzoomedReticleDisplay,
    };
    void fetchMapPointsForTab(tabs.value[idx]);
  }

  function rowKey(row: InspectionSummaryItem): string {
    return `${row.inspection_time}_${row.wafer_key}`;
  }

  function rowProps(row: InspectionSummaryItem): Record<string, unknown> {
    return {
      style: { cursor: "pointer" },
      onClick: () => openInspectionTab(row),
    };
  }

  // ── Search ───────────────────────────────────────

  async function searchInspections(): Promise<void> {
    const range = dateRange.value;
    if (!range) return;

    const startVal = range[0];
    const endVal = range[1];

    const pad = (n: number) => String(n).padStart(2, "0");
    const fmt = (ts: number) => {
      const d = new Date(ts);
      return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
    };
    const start = fmt(startVal);
    const end = fmt(endVal);

    summariesEmpty.value = false;
    summariesLoading.value = true;
    summariesError.value = null;

    const nextSearchParams: GetInspectionsApiV1ScInspectionsGetParams = {
      start_time: start,
      end_time: end,
    };
    const lotId = lotIdFilter.value.trim();
    const eqpId = eqpIdFilter.value.trim();
    const layerId = layerIdFilter.value.trim();
    const device = deviceFilter.value.trim();
    if (lotId) nextSearchParams.lot_id = lotId;
    if (eqpId) nextSearchParams.eqp_id = eqpId;
    if (layerId) nextSearchParams.layer_id = layerId;
    if (device) nextSearchParams.device = device;

    searchParams.value = nextSearchParams;
    searchNonce.value += 1;

    try {
      const { data } = await inspectionsQuery.refetch({ throwOnError: true });
      const payload = data?.data;
      if (payload && "items" in payload) {
        const items = payload.items;
        summaries.value = items;
        summariesEmpty.value = items.length === 0;
      } else {
        summaries.value = [];
        summariesEmpty.value = true;
      }
    } catch (err) {
      summariesError.value =
        err instanceof Error ? err.message : "Failed to fetch inspections";
      summaries.value = [];
    } finally {
      summariesLoading.value = false;
    }
  }

  // ── Watcher ──────────────────────────────────────

  watch(
    () => route.query.datasetId,
    (val) => {
      if (typeof val === "string" && val !== datasetId.value) {
        datasetId.value = val;
      }
    },
  );

  // ── Import modal state ───────────────────────────

  const showImportModal = ref(false);
  const importSourceInspectionTime = ref("");
  const importSourceWaferKey = ref(0);
  const importDatasetName = ref("");
  const importStorageMode = ref<"file_shard_sparse">("file_shard_sparse");
  const isImporting = ref(false);
  const importProgress = ref<ScImportProgressEvent>({
    status: "",
    imported_count: 0,
    remaining_count: 0,
  });
  const importError = ref("");

  createSummaryTab();

  const storageModeOptions = [
    { label: "Sparse Shard (file_shard_sparse)", value: "file_shard_sparse" },
  ];

  function sanitizeInspectionTime(inspectionTime: string): string {
    return inspectionTime.replace(/[\s:]/g, "-");
  }

  function openImportForInspection(item: InspectionSummaryItem): void {
    importError.value = "";
    importSourceInspectionTime.value = item.inspection_time;
    importSourceWaferKey.value = item.wafer_key;
    importDatasetName.value = `Patch_${item.lot_id}_${item.wafer_id}_${sanitizeInspectionTime(item.inspection_time)}`;
    showImportModal.value = true;
  }

  function startImportDirectly(item: InspectionSummaryItem): void {
    importError.value = "";
    importSourceInspectionTime.value = item.inspection_time;
    importSourceWaferKey.value = item.wafer_key;
    importDatasetName.value = `Patch_${item.lot_id}_${item.wafer_id}_${sanitizeInspectionTime(item.inspection_time)}`;
    void handleImport();
  }

  // ── Import handlers ──────────────────────────────

  async function handleImport(): Promise<void> {
    importError.value = "";
    isImporting.value = true;
    importProgress.value = {
      status: "",
      imported_count: 0,
      remaining_count: 0,
    };

    try {
      const req: ScImportPayload = {
        source_inspection_time: importSourceInspectionTime.value.trim(),
        source_wafer_key: importSourceWaferKey.value,
        dataset_name: importDatasetName.value.trim(),
        storage_mode: importStorageMode.value,
      };
      const dataEvent = await streamApiSse("/sc/import/stream", {
        method: "POST",
        body: req,
        onEvent: (event) => {
          if (event.event_type !== "progress") return;
          const importedCount = Number(
            event.imported_count ?? event.loaded_count ?? 0,
          );
          const totalCount = Number(event.total_count ?? 0);
          importProgress.value = {
            status: event.status ?? "running",
            imported_count: importedCount,
            remaining_count:
              totalCount > 0 ? Math.max(totalCount - importedCount, 0) : 0,
            dataset_id: event.dataset_id,
          };
        },
      });
      const payload = dataEvent?.payload ?? {};
      const resp: ScImportResponse = {
        status: typeof payload.status === "string" ? payload.status : "failed",
        dataset_id:
          typeof payload.dataset_id === "string" ? payload.dataset_id : undefined,
        imported_count:
          typeof payload.imported_count === "number" ? payload.imported_count : 0,
        error: typeof payload.error === "string" ? payload.error : null,
      };
      isImporting.value = false;
      showImportModal.value = false;
      if (resp.status === "completed" && resp.dataset_id) {
        datasetId.value = resp.dataset_id;
        importProgress.value = {
          status: resp.status,
          imported_count: resp.imported_count ?? 0,
          remaining_count: 0,
        };
        message.success(
          `Import complete: ${resp.imported_count ?? 0} samples imported`,
        );
        window.open(`/datasets/${resp.dataset_id}/sc/classify`, "_blank");
      } else if (resp.status === "failed") {
        message.error(resp.error || "Import failed");
      }
    } catch (err: unknown) {
      isImporting.value = false;
      importError.value = err instanceof Error ? err.message : String(err);
    }
  }

  onMounted(() => {
    searchInspections();
  });

  return {
    datasetId,
    dateRange,
    lotIdFilter,
    eqpIdFilter,
    layerIdFilter,
    deviceFilter,
    classifyHref,

    summaries,
    summariesLoading,
    summariesError,
    summariesEmpty,
    inspectionColumns,

    tabs,
    activeTabId,
    activeTab,

    searchInspections,
    createSummaryTab,
    openInspectionTab,
    closeTab,
    fetchSamplesForTab,
    fetchPreviewDataForTab,
    setMapTab,
    setZoom,
    updateReticleOptions,
    setSelectedDefectIds,
    handleTableFilterChange,
    handleTableSortChange,
    handleLegendGroupByChange,
    rowKey,
    rowProps,

    showImportModal,
    importSourceInspectionTime,
    importSourceWaferKey,
    importDatasetName,
    importStorageMode,
    isImporting,
    importProgress,
    importError,
    storageModeOptions,
    handleImport,
    openImportForInspection,
    startImportDirectly,
  };
}
