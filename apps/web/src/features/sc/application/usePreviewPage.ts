import { computed, onMounted, ref, watch, type ComputedRef, type Ref } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import { useMessage } from "naive-ui";
import type { DataTableColumns } from "naive-ui";
import { getInspectionsApiV1ScInspectionsGet } from "@/generated/orval/endpoints/api";
import { streamApiSse } from "@/shared/api/sse";
import { create } from "@bufbuild/protobuf";
import { type DefectList, ScSampleItemSchema } from "../generated/proto/sc/v1/sample_pb";
import type { ScSampleItem } from "../generated/proto/sc/v1/sample_pb";
import type {
  InspectionSummaryItem,
  ScImportProgressEvent,
  ScImportPayload,
  ScImportResponse,
} from "../domain/models";
import type { GetInspectionsApiV1ScInspectionsGetParams } from "@/generated/orval/models/getInspectionsApiV1ScInspectionsGetParams";
import type { ScSampleTableFilter, ScSampleTableSort } from "../domain/sampleTable";
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
  lastOpenedSummaryKey: Ref<string | null>;
  lastOpenedSummaryLabel: ComputedRef<string | null>;

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
  updateReticleOptions: (tabId: string, options: ReticleMapOptions) => Promise<void>;
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
  importingInspectionKey: Ref<string | null>;
  importProgress: Ref<ScImportProgressEvent>;
  importError: Ref<string>;
  storageModeOptions: { label: string; value: string }[];
  handleImport: () => Promise<void>;
  importInspection: (
    item: InspectionSummaryItem,
    notify?: boolean,
    forceNew?: boolean,
  ) => Promise<string>;
  openImportForInspection: (item: InspectionSummaryItem) => void;
  startImportDirectly: (item: InspectionSummaryItem) => void;
  importedDatasetIdForInspection: (item: InspectionSummaryItem) => string | null;
}

// ── Composable ────────────────────────────────────────────────────────

export function usePreviewPage(): PreviewPageState {
  const route = useRoute();
  const message = useMessage();
  const { t } = useI18n();

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
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
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
  const lastOpenedSummaryKey = ref<string | null>(null);
  const lastOpenedSummaryLabel = computed(() => {
    const key = lastOpenedSummaryKey.value;
    if (!key) return null;
    const row = summaries.value.find((item) => rowKey(item) === key);
    if (!row) return t("sc.summaryOutsideResults");
    const lot = row.lot_id ? `${row.lot_id} / ` : "";
    return `${lot}W${row.wafer_key} · ${formatInspectionTime(row.inspection_time)}`;
  });

  type SummaryFilterKey =
    | "inspection_time"
    | "lot_id"
    | "wafer_id"
    | "layer_id"
    | "device"
    | "eqp_id"
    | "recipe_id";
  type SummaryFilterOptionKey = Exclude<SummaryFilterKey, "inspection_time">;

  const SUMMARY_FILTER_OPTION_LIMIT = 500;
  const inspectionTimeLabelCache = new Map<string, string>();
  const inspectionTimeEpochCache = new Map<string, number>();

  function parseInspectionTime(value: string): number {
    const cached = inspectionTimeEpochCache.get(value);
    if (cached !== undefined) return cached;
    const parsed = Date.parse(value);
    const epoch = Number.isFinite(parsed) ? parsed : 0;
    inspectionTimeEpochCache.set(value, epoch);
    return epoch;
  }

  function formatInspectionTime(value: string): string {
    const cached = inspectionTimeLabelCache.get(value);
    if (cached !== undefined) return cached;
    const parsed = parseInspectionTime(value);
    const label = parsed > 0 ? new Date(parsed).toLocaleString() : value;
    inspectionTimeLabelCache.set(value, label);
    return label;
  }

  function summaryFilterLabel(key: SummaryFilterKey, value: string): string {
    return key === "inspection_time" ? formatInspectionTime(value) : value;
  }

  function summaryFilterOptions(key: SummaryFilterKey) {
    return summaryFilterOptionsByKey.value[key];
  }

  const summaryFilterOptionsByKey = computed<
    Record<SummaryFilterKey, { label: string; value: string }[]>
  >(() => {
    const valuesByKey: Record<SummaryFilterOptionKey, Set<string>> = {
      lot_id: new Set(),
      wafer_id: new Set(),
      layer_id: new Set(),
      device: new Set(),
      eqp_id: new Set(),
      recipe_id: new Set(),
    };
    const filterKeys = Object.keys(valuesByKey) as SummaryFilterOptionKey[];
    for (const row of summaries.value) {
      for (const key of filterKeys) {
        const value = row[key];
        if (value !== undefined && value !== null && String(value).length > 0) {
          valuesByKey[key].add(String(value));
        }
      }
    }
    const result: Record<SummaryFilterKey, { label: string; value: string }[]> = {
      inspection_time: [],
      lot_id: [],
      wafer_id: [],
      layer_id: [],
      device: [],
      eqp_id: [],
      recipe_id: [],
    };
    for (const key of filterKeys) {
      if (valuesByKey[key].size > SUMMARY_FILTER_OPTION_LIMIT) {
        result[key] = [];
        continue;
      }
      result[key] = [...valuesByKey[key]]
        .sort((left, right) => left.localeCompare(right, undefined, { numeric: true }))
        .map((value) => ({ label: summaryFilterLabel(key, value), value }));
    }
    return result;
  });

  function summaryStringSorter(
    key: SummaryFilterKey,
  ): (left: InspectionSummaryItem, right: InspectionSummaryItem) => number {
    return (left, right) =>
      String(left[key] ?? "").localeCompare(String(right[key] ?? ""), undefined, {
        numeric: true,
      });
  }

  function summaryStringFilter(
    key: SummaryFilterKey,
  ): (value: string | number, row: InspectionSummaryItem) => boolean {
    return (value, row) => String(row[key] ?? "") === String(value);
  }

  function summaryNumberSorter(
    key: "defects" | "images",
  ): (left: InspectionSummaryItem, right: InspectionSummaryItem) => number {
    return (left, right) => Number(left[key]) - Number(right[key]);
  }

  const inspectionColumns = computed<DataTableColumns<InspectionSummaryItem>>(() => [
    {
      key: "inspection_time",
      title: t("sc.inspectionTime"),
      width: 200,
      ellipsis: { tooltip: true },
      sorter: (left, right) =>
        parseInspectionTime(left.inspection_time) - parseInspectionTime(right.inspection_time),
      render: (row) => formatInspectionTime(row.inspection_time),
    },
    {
      key: "lot_id",
      title: t("sc.lotId"),
      width: 100,
      sorter: summaryStringSorter("lot_id"),
      filter: summaryStringFilter("lot_id"),
      filterOptions: summaryFilterOptions("lot_id"),
      filterMultiple: true,
    },
    {
      key: "wafer_id",
      title: t("sc.waferId"),
      width: 80,
      sorter: summaryStringSorter("wafer_id"),
      filter: summaryStringFilter("wafer_id"),
      filterOptions: summaryFilterOptions("wafer_id"),
      filterMultiple: true,
    },
    {
      key: "layer_id",
      title: t("sc.layerId"),
      width: 80,
      sorter: summaryStringSorter("layer_id"),
      filter: summaryStringFilter("layer_id"),
      filterOptions: summaryFilterOptions("layer_id"),
      filterMultiple: true,
    },
    {
      key: "device",
      title: t("sc.device"),
      width: 90,
      sorter: summaryStringSorter("device"),
      filter: summaryStringFilter("device"),
      filterOptions: summaryFilterOptions("device"),
      filterMultiple: true,
    },
    {
      key: "defects",
      title: t("sc.defects"),
      width: 80,
      sorter: summaryNumberSorter("defects"),
    },
    {
      key: "images",
      title: t("sc.images"),
      width: 120,
      ellipsis: { tooltip: true },
      sorter: summaryNumberSorter("images"),
    },
    {
      key: "eqp_id",
      title: t("sc.equipmentId"),
      width: 120,
      sorter: summaryStringSorter("eqp_id"),
      filter: summaryStringFilter("eqp_id"),
      filterOptions: summaryFilterOptions("eqp_id"),
      filterMultiple: true,
    },
    {
      key: "recipe_id",
      title: t("sc.recipeId"),
      width: 120,
      sorter: summaryStringSorter("recipe_id"),
      filter: summaryStringFilter("recipe_id"),
      filterOptions: summaryFilterOptions("recipe_id"),
      filterMultiple: true,
    },
  ]);

  // ── Tab system ───────────────────────────────────

  const tabs = ref<PreviewTab[]>([]);
  const activeTabId = ref<string | null>(null);
  const activeTab = computed(() => tabs.value.find((t) => t.id === activeTabId.value) ?? null);

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
      label: t("sc.summary"),
      pinned: true,
      samples: [],
      samplesTotal: 0,
      samplesLoading: false,
      samplesError: null,
      patchSamples: [],
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
    lastOpenedSummaryKey.value = rowKey(row);
    const id = `tab-${nextTabId++}`;
    const label = row.lot_id ? `${row.lot_id}#${row.wafer_id}` : `W${row.wafer_key}`;
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
      samplesLoading: false,
      samplesError: null,
      patchSamples: makePatchSamples(row),
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
    const inspectionTime = inspectionTimeEpochSeconds(row.inspection_time);
    return [
      create(ScSampleItemSchema, {
        defectId: 0,
        inspectionTime,
        waferKey: row.wafer_key,
        reviewImages: [],
      }),
    ];
  }

  async function fetchPreviewDataForTab(tab: PreviewTab): Promise<void> {
    const idx = tabs.value.findIndex((t) => t.id === tab.id);
    if (idx !== -1) tabs.value[idx] = { ...tabs.value[idx], mapLoading: false };
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
        tabs.value.length > 0 ? tabs.value[Math.min(idx, tabs.value.length - 1)].id : null;
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
      mapLoading: false,
      mapError: null,
      mapStreamMessage: "",
      mapProgressPercent: 0,
    };
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
      unzoomedReticleDisplay: [],
      mapError: null,
      mapStreamMessage: "",
      mapProgressPercent: 0,
    };
  }

  function setSelectedDefectIds(tabId: string, ids: number[]): void {
    const idx = tabs.value.findIndex((t) => t.id === tabId);
    if (idx === -1) return;
    tabs.value[idx] = {
      ...tabs.value[idx],
      selectedDefectIds: ids,
    };
  }

  function handleTableFilterChange(tabId: string, filter: ScSampleTableFilter): void {
    const idx = tabs.value.findIndex((t) => t.id === tabId);
    if (idx === -1) return;
    tabs.value[idx] = {
      ...tabs.value[idx],
      tableFilter: filter,
      zoom: null,
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
      tableSort: sort.direction ? { field: sort.field, direction: sort.direction } : null,
    };
  }

  function handleLegendGroupByChange(tabId: string, groupBy: string | null): void {
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
    if (!range || summariesLoading.value) return;

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

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15_000);

    try {
      const payload = await getInspectionsApiV1ScInspectionsGet(nextSearchParams, {
        signal: controller.signal,
      });
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
        err instanceof DOMException && err.name === "AbortError"
          ? t("sc.inspectionSearchTimeout")
          : err instanceof Error
            ? err.message
            : t("sc.inspectionLoadFailed");
      summaries.value = [];
    } finally {
      clearTimeout(timeoutId);
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
  const importingInspectionKey = ref<string | null>(null);
  const importProgress = ref<ScImportProgressEvent>({
    status: "",
    imported_count: 0,
    remaining_count: 0,
  });
  const importError = ref("");
  const importedDatasetIdsByInspection = ref<Record<string, string>>({});

  createSummaryTab();

  const storageModeOptions = [{ label: t("sc.sparseShard"), value: "file_shard_sparse" }];

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

  function importKey(inspectionTime: string, waferKey: number): string {
    return `${inspectionTime}::${waferKey}`;
  }

  function importedDatasetIdForInspection(item: InspectionSummaryItem): string | null {
    return (
      importedDatasetIdsByInspection.value[importKey(item.inspection_time, item.wafer_key)] ??
      item.datasets?.[0]?.id ??
      null
    );
  }

  // ── Import handlers ──────────────────────────────

  async function runImport(req: ScImportPayload, notify: boolean): Promise<string> {
    importError.value = "";
    isImporting.value = true;
    importProgress.value = {
      status: "",
      imported_count: 0,
      remaining_count: 0,
    };

    try {
      const dataEvent = await streamApiSse("/sc/import/stream", {
        method: "POST",
        body: req,
        onEvent: (event) => {
          if (event.event_type !== "progress") return;
          const importedCount = Number(event.imported_count ?? event.loaded_count ?? 0);
          const totalCount = Number(event.total_count ?? 0);
          importProgress.value = {
            status: event.status ?? "running",
            imported_count: importedCount,
            remaining_count: totalCount > 0 ? Math.max(totalCount - importedCount, 0) : 0,
            dataset_id: event.dataset_id,
          };
        },
      });
      const payload = dataEvent?.payload ?? {};
      const resp: ScImportResponse = {
        status: typeof payload.status === "string" ? payload.status : "failed",
        dataset_id: typeof payload.dataset_id === "string" ? payload.dataset_id : undefined,
        imported_count: typeof payload.imported_count === "number" ? payload.imported_count : 0,
        error: typeof payload.error === "string" ? payload.error : null,
      };
      showImportModal.value = false;
      if (resp.status === "completed" && resp.dataset_id) {
        datasetId.value = resp.dataset_id;
        importedDatasetIdsByInspection.value = {
          ...importedDatasetIdsByInspection.value,
          [importKey(req.source_inspection_time, req.source_wafer_key)]: resp.dataset_id,
        };
        importProgress.value = {
          status: resp.status,
          imported_count: resp.imported_count ?? 0,
          remaining_count: 0,
        };
        if (notify) {
          message.success(t("sc.importComplete", { count: resp.imported_count ?? 0 }));
        }
        return resp.dataset_id;
      }
      throw new Error(resp.error || t("sc.importFailed"));
    } catch (err: unknown) {
      importError.value = err instanceof Error ? err.message : String(err);
      if (notify) message.error(importError.value);
      throw err;
    } finally {
      isImporting.value = false;
    }
  }

  async function importInspection(
    item: InspectionSummaryItem,
    notify = true,
    forceNew = false,
  ): Promise<string> {
    const existing = forceNew ? null : importedDatasetIdForInspection(item);
    if (existing) return existing;
    const baseDatasetName = `Patch_${item.lot_id}_${item.wafer_id}_${sanitizeInspectionTime(item.inspection_time)}`;
    const existingDatasetCount = item.datasets?.length ?? 0;
    const datasetName =
      forceNew && existingDatasetCount > 0
        ? `${baseDatasetName}_${existingDatasetCount + 1}`
        : baseDatasetName;
    const key = rowKey(item);
    importingInspectionKey.value = key;
    try {
      const datasetId = await runImport(
        {
          source_inspection_time: item.inspection_time,
          source_wafer_key: item.wafer_key,
          dataset_name: datasetName,
          storage_mode: importStorageMode.value,
        },
        notify,
      );
      summaries.value = summaries.value.map((summary) =>
        rowKey(summary) === key
          ? {
              ...summary,
              datasets: [...(summary.datasets ?? []), { id: datasetId, name: datasetName }],
            }
          : summary,
      );
      return datasetId;
    } finally {
      if (importingInspectionKey.value === key) importingInspectionKey.value = null;
    }
  }

  async function handleImport(): Promise<void> {
    try {
      await runImport(
        {
          source_inspection_time: importSourceInspectionTime.value.trim(),
          source_wafer_key: importSourceWaferKey.value,
          dataset_name: importDatasetName.value.trim(),
          storage_mode: importStorageMode.value,
        },
        true,
      );
    } catch {
      // runImport already records and surfaces the transport error.
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
    lastOpenedSummaryKey,
    lastOpenedSummaryLabel,

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
    importingInspectionKey,
    importProgress,
    importError,
    storageModeOptions,
    handleImport,
    importInspection,
    openImportForInspection,
    startImportDirectly,
    importedDatasetIdForInspection,
  };
}
