import {
  computed,
  onMounted,
  onUnmounted,
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
  useStartScImportApiV1ScImportPost,
  getInspectionReviewImagesApiV1ScInspectionsInspectionTimeWaferKeyReviewImagesGet,
} from "@/generated/orval/endpoints/api";
import { getApiBase } from "@/shared/api/client";
import { withAuthQueryParams } from "@/shared/api/client";
import { create, fromBinary } from "@bufbuild/protobuf";
import {
  type ClassList,
  ReviewImageSchema,
  ScSampleItemSchema,
  WaferMapResponseSchema,
} from "../generated/proto/sc/v1/sample_pb";
import { fetchScInspectionClassList } from "../api/classList";
import type { ScSampleItem } from "../generated/proto/sc/v1/sample_pb";
import type {
  InspectionSummaryItem,
  ScImportProgressEvent,
  ScImportPayload,
  ScImportResponse,
} from "../domain/models";
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
  /** Full (unsampled) arrays for selection spatial index — populated via second request when total >= 50000 */
  fullWaferDisplay: number[];
  fullDieDisplay: number[];
  fullReticleDisplay: number[];
  classList: ClassList | null;
  reticleXDieCount: number;
  reticleYDieCount: number;
  reticleDieSizeX: number;
  reticleDieSizeY: number;
  reticleOptions: ReticleMapOptions;
  zoom: { x: number; y: number; w: number; h: number } | null;
}

type MapMode = "wafer" | "die" | "reticle";

// ── Composable result type ────────────────────────────────────────────

export interface PreviewPageState {
  datasetId: Ref<string>;
  dateRange: Ref<[number, number] | null>;
  classifyHref: ComputedRef<string>;

  summaries: Ref<InspectionSummaryItem[]>;
  summariesLoading: Ref<boolean>;
  summariesError: Ref<string | null>;
  summariesEmpty: Ref<boolean>;
  inspectionColumns: DataTableColumns<InspectionSummaryItem>;

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
  setZoom: (tabId: string, vp: { x: number; y: number; w: number; h: number } | null) => Promise<void>;
  updateReticleOptions: (tabId: string, options: ReticleMapOptions) => Promise<void>;
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
    const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
    const yesterday = today - 24 * 60 * 60 * 1000;
    const tomorrow = today + 24 * 60 * 60 * 1000;
    return [yesterday, tomorrow];
  }

  const dateRange = ref<[number, number] | null>(getDefaultDateRange());

  // ── Inspection summaries (JSON, snake_case) ─────

  const summaries = ref<InspectionSummaryItem[]>([]);
  const summariesLoading = ref(false);
  const summariesError = ref<string | null>(null);
  const summariesEmpty = ref(false);

  const searchParams = ref<{ start_time: string; end_time: string } | null>(
    null,
  );

  const searchNonce = ref(0);

  const inspectionsQuery = useGetInspectionsApiV1ScInspectionsGet(
    computed(
      () => searchParams.value ?? { start_time: "", end_time: "" },
    ),
    {
      query: {
        enabled: computed(() => searchParams.value !== null),
        staleTime: 0,
        queryKey: computed(() => [
          "api",
          "v1",
          "sc",
          "inspections",
          searchNonce.value,
          searchParams.value ?? { start_time: "", end_time: "" },
        ] as const),
      },
    },
  );

  const inspectionColumns: DataTableColumns<InspectionSummaryItem> = [
    {
      key: "inspection_time",
      title: "Inspection Time",
      width: 200,
      ellipsis: { tooltip: true },
    },
    { key: "lot_id", title: "Lot ID", width: 100 },
    { key: "wafer_id", title: "Wafer ID", width: 80 },
    { key: "layer_id", title: "Layer ID", width: 80 },
    { key: "defects", title: "Defects", width: 80 },
    { key: "images", title: "Images", width: 120, ellipsis: { tooltip: true } },
    { key: "eqp_id", title: "Equipment ID", width: 80 },
    { key: "recipe_id", title: "Recipe ID", width: 80 },
  ];

  // ── Tab system ───────────────────────────────────

  const tabs = ref<PreviewTab[]>([]);
  const activeTabId = ref<string | null>(null);
  const activeTab = computed(
    () => tabs.value.find((t) => t.id === activeTabId.value) ?? null,
  );

  let nextTabId = 1;

  function createSummaryTab(): void {
    const id = `tab-${nextTabId++}`;
    tabs.value.push({
      id,
      type: "summary",
      label: "Summary",
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
      activeMapTab: "wafer",
      waferGeometry: null,
      waferDisplay: [],
      dieDisplay: [],
      reticleDisplay: [],
      fullWaferDisplay: [],
      fullDieDisplay: [],
      fullReticleDisplay: [],
      classList: null,
      reticleXDieCount: 10,
      reticleYDieCount: 10,
      reticleDieSizeX: 100000,
      reticleDieSizeY: 100000,
      reticleOptions: { ...DEFAULT_RETICLE_MAP_OPTIONS },
      zoom: null,
    });
    activeTabId.value = id;
  }

  function openInspectionTab(row: InspectionSummaryItem): void {
    const id = `tab-${nextTabId++}`;
    const label = row.lot_id
      ? `${row.lot_id} / W${row.wafer_key}`
      : `W${row.wafer_key}`;
    const reticleOptions = normalizeReticleMapOptions(DEFAULT_RETICLE_MAP_OPTIONS);
    const tab: PreviewTab = {
      id,
      type: "inspection",
      label,
      inspectionTime: row.inspection_time,
      waferKey: row.wafer_key,
      inspectionItem: row,
      samples: [],
      samplesTotal: row.defects,
      zoom: null,
      samplesLoading: false,
      samplesError: null,
      patchSamples: makePatchSamples(row),
      reviewSamples: [],
      reviewLoading: true,
      reviewError: null,
      mapLoading: true,
      mapError: null,
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
      fullWaferDisplay: [],
      fullDieDisplay: [],
      fullReticleDisplay: [],
      classList: null,
      reticleXDieCount: reticleOptions.xDieCount,
      reticleYDieCount: reticleOptions.yDieCount,
      reticleDieSizeX: row.die_size_x || 100000,
      reticleDieSizeY: row.die_size_y || 100000,
      reticleOptions,
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
    const total = Math.max(0, row.defects ?? 0);
    const inspectionTime = inspectionTimeEpochSeconds(row.inspection_time);
    return Array.from({ length: total }, (_, i) =>
      create(ScSampleItemSchema, {
        defectId: i + 1,
        inspectionTime,
        waferKey: row.wafer_key,
        reviewImages: [],
      }),
    );
  }

  async function fetchPreviewDataForTab(tab: PreviewTab): Promise<void> {
    await Promise.allSettled([
      fetchMapPointsForTab(tab),
      fetchClassListForTab(tab),
      fetchReviewImagesForTab(tab),
    ]);
  }

  async function fetchMapPointsForTab(
    tab: PreviewTab,
    modes: MapMode[] = ["wafer", "die", "reticle"],
  ): Promise<void> {
    const tabId = tab.id;
    if (!tab.inspectionTime || tab.waferKey === undefined) return;
    const idx = tabs.value.findIndex((t) => t.id === tabId);
    if (idx === -1) return;
    tabs.value[idx] = { ...tabs.value[idx], mapLoading: true, mapError: null };

    const opts = normalizeReticleMapOptions(tab.reticleOptions);
    try {
      const results = await Promise.all(
        modes.map(async (mode) => ({
          mode,
          result: await _fetchMapData(tab, mode, opts),
        })),
      );

      const idx2 = tabs.value.findIndex((t) => t.id === tabId);
      if (idx2 === -1) return;

      const current = tabs.value[idx2];
      const firstResult = results[0]?.result;
      const geo = firstResult?.geometry;
      const baseUpdate: Partial<PreviewTab> = {
        mapLoading: false,
        waferGeometry: geo ? {
          waferRadiusNm: geo.waferRadiusNm,
          centerX: geo.centerX,
          centerY: geo.centerY,
          originX: geo.originX,
          originY: geo.originY,
          dieSizeX: geo.dieSizeX,
          dieSizeY: geo.dieSizeY,
        } : tabs.value[idx2].waferGeometry,
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
      };
      for (const { mode, result } of results) {
        if (mode === "wafer") baseUpdate.waferDisplay = result.waferPoints;
        if (mode === "die") baseUpdate.dieDisplay = result.diePoints;
        if (mode === "reticle") baseUpdate.reticleDisplay = result.reticlePoints;
      }
      tabs.value[idx2] = {
        ...current,
        ...baseUpdate,
        fullWaferDisplay: current.zoom
          ? current.fullWaferDisplay
          : baseUpdate.waferDisplay
            ?? current.fullWaferDisplay,
        fullDieDisplay: current.zoom
          ? current.fullDieDisplay
          : baseUpdate.dieDisplay
            ?? current.fullDieDisplay,
        fullReticleDisplay: current.zoom
          ? current.fullReticleDisplay
          : baseUpdate.reticleDisplay
            ?? current.fullReticleDisplay,
      };
    } catch (err) {
      const idx2 = tabs.value.findIndex((t) => t.id === tabId);
      if (idx2 !== -1) {
        tabs.value[idx2] = {
          ...tabs.value[idx2],
          mapLoading: false,
          mapError: err instanceof Error ? err.message : "Failed to fetch map points",
        };
      }
    }
  }

  async function fetchClassListForTab(tab: PreviewTab): Promise<void> {
    if (!tab.inspectionTime || tab.waferKey === undefined) return;
    const classList = await fetchScInspectionClassList(
      tab.inspectionTime,
      tab.waferKey,
    );
    const idx = tabs.value.findIndex((item) => item.id === tab.id);
    if (idx !== -1) {
      tabs.value[idx] = { ...tabs.value[idx], classList };
    }
  }

  async function _fetchMapData(
    tab: PreviewTab,
    mode: MapMode,
    opts: ReturnType<typeof normalizeReticleMapOptions>,
  ) {
    const params = new URLSearchParams();
    params.set("mode", mode);
    params.set("sampled", "true");
    params.set("gridSizeNm", "600");
    params.set("reticleXDieCount", String(opts.xDieCount));
    params.set("reticleYDieCount", String(opts.yDieCount));
    params.set("reticleXDieShift", String(opts.xDieShift));
    params.set("reticleYDieShift", String(opts.yDieShift));
    if (tab.zoom) {
      params.set("zoomX", String(Math.round(tab.zoom.x)));
      params.set("zoomY", String(Math.round(tab.zoom.y)));
      params.set("zoomW", String(Math.round(tab.zoom.w)));
      params.set("zoomH", String(Math.round(tab.zoom.h)));
    }
    let url = `${getApiBase()}/sc/inspections/${tab.inspectionTime}/${tab.waferKey}/map-points?${params.toString()}`;
    url = withAuthQueryParams(url);
    const resp = await fetch(url, { headers: { Accept: "application/x-protobuf" } });
    if (!resp.ok) throw new Error(`Map points request failed: ${resp.status}`);
    const blob = await resp.blob();
    return fromBinary(WaferMapResponseSchema, new Uint8Array(await blob.arrayBuffer()));
  }

  async function fetchReviewImagesForTab(tab: PreviewTab): Promise<void> {
    const tabId = tab.id;
    if (!tab.inspectionTime || tab.waferKey === undefined) return;
    const idx = tabs.value.findIndex((t) => t.id === tabId);
    if (idx === -1) return;
    tabs.value[idx] = { ...tabs.value[idx], reviewLoading: true, reviewError: null };
    try {
      const { data } = await getInspectionReviewImagesApiV1ScInspectionsInspectionTimeWaferKeyReviewImagesGet(
        tab.inspectionTime,
        tab.waferKey,
      );
      if (!data || !("items" in data)) throw new Error("Invalid review images response");
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
          reviewError: err instanceof Error ? err.message : "Failed to fetch review images",
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
        waferDisplay: tab.fullWaferDisplay,
        dieDisplay: tab.fullDieDisplay,
        reticleDisplay: tab.fullReticleDisplay,
      };
    }
  }

  async function setZoom(tabId: string, vp: { x: number; y: number; w: number; h: number } | null): Promise<void> {
    const idx = tabs.value.findIndex((t) => t.id === tabId);
    if (idx === -1) return;
    const tab = tabs.value[idx];
    if (vp === null) {
      tabs.value[idx] = {
        ...tab,
        zoom: null,
        mapLoading: false,
        mapError: null,
        waferDisplay: tab.fullWaferDisplay,
        dieDisplay: tab.fullDieDisplay,
        reticleDisplay: tab.fullReticleDisplay,
      };
      return;
    }
    tabs.value[idx] = { ...tab, zoom: vp, mapLoading: true, mapError: null };
    await fetchMapPointsForTab(tabs.value[idx], [tab.activeMapTab]);
  }

  async function updateReticleOptions(tabId: string, options: ReticleMapOptions): Promise<void> {
    const idx = tabs.value.findIndex((t) => t.id === tabId);
    if (idx === -1) return;
    const normalized = normalizeReticleMapOptions(options);
    tabs.value[idx] = {
      ...tabs.value[idx],
      reticleOptions: normalized,
      reticleXDieCount: normalized.xDieCount,
      reticleYDieCount: normalized.yDieCount,
      reticleDisplay: [],
      fullReticleDisplay: [],
      mapError: null,
    };
    await fetchMapPointsForTab(tabs.value[idx], ["reticle"]);
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

    searchParams.value = { start_time: start, end_time: end };
    searchNonce.value += 1;

    try {
      const { data } = await inspectionsQuery.refetch({ throwOnError: true });
      const payload = data?.data;
      if (payload && "items" in payload) {
        const items = payload.items;
        summaries.value = items;
        summariesEmpty.value = items.length === 0;
        if (tabs.value.length === 0) {
          createSummaryTab();
        }
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
  const importEventSource = ref<EventSource | null>(null);
  const openedImportDatasetId = ref("");

  const importMutation = useStartScImportApiV1ScImportPost();

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

  function connectImportSSE(runId: string, importedDatasetId?: string): void {
    const url = `${getApiBase()}/sc/import/${runId}/stream`;
    const token = localStorage.getItem("auth_token") || "";
    const params = new URLSearchParams();
    if (token) params.set("token", token);
    if (importedDatasetId) params.set("dataset_id", importedDatasetId);
    const query = params.toString();
    const esUrl = query ? `${url}?${query}` : url;
    const es = new EventSource(esUrl);

    es.addEventListener("progress", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as ScImportProgressEvent;
        importProgress.value = {
          status: data.status || "",
          imported_count: data.imported_count || 0,
          remaining_count: data.remaining_count || 0,
        };
        if (data.dataset_id && data.dataset_id !== openedImportDatasetId.value) {
          openedImportDatasetId.value = data.dataset_id;
          datasetId.value = data.dataset_id;
          showImportModal.value = false;
          message.success(
            `Samples are available in dataset: ${data.dataset_id}. Import continues in the background.`,
          );
          window.open(`/datasets/${data.dataset_id}/sc/classify`, "_blank");
        }
      } catch {
        /* ignore parse errors */
      }
    });

    es.addEventListener("done", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as ScImportProgressEvent;
        isImporting.value = false;
        showImportModal.value = false;
        es.close();
        if (data.dataset_id && data.dataset_id !== openedImportDatasetId.value) {
          message.success(`Dataset created: ${data.dataset_id}`);
          window.open(`/datasets/${data.dataset_id}/sc/classify`, "_blank");
        }
      } catch {
        /* ignore */
      }
    });

    es.addEventListener("error", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data || "{}") as ScImportProgressEvent;
        importError.value = data.error || "Import failed";
      } catch {
        importError.value = "Import failed";
      }
      isImporting.value = false;
      es.close();
    });

    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) {
        importError.value = "Connection lost";
        isImporting.value = false;
      }
    };

    importEventSource.value = es;
  }

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
      const orvalResp = await importMutation.mutateAsync({ data: req });
      const resp = orvalResp.data as ScImportResponse;
      if (resp.flow_run_id && resp.status !== "failed") {
        message.info("Import started. The dataset will open after the first samples are available.");
        connectImportSSE(resp.flow_run_id, resp.dataset_id || undefined);
      } else {
        isImporting.value = false;
        showImportModal.value = false;
        if (resp.status === "failed") {
          message.error(resp.error || "Import failed");
        }
      }
    } catch (err: unknown) {
      isImporting.value = false;
      importError.value = err instanceof Error ? err.message : String(err);
    }
  }

  onMounted(() => {
    searchInspections();
  });

  // ── Cleanup SSE on unmount ──────────────────────

  onUnmounted(() => {
    importEventSource.value?.close();
  });

  return {
    datasetId,
    dateRange,
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
