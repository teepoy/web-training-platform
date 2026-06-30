import { computed, ref, watch, type ComputedRef, type Ref } from "vue";
import { create } from "@bufbuild/protobuf";
import type { Filter, Table, View, ViewConfigUpdate } from "@perspective-dev/client";
import type { DefectList, ScSampleItem } from "@/features/sc/generated/proto/sc/v1/sample_pb";
import {
  DefectListSchema,
  ReviewImageSchema,
  ScSampleItemSchema,
} from "@/features/sc/generated/proto/sc/v1/sample_pb";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type { ScLegendSource } from "@/features/sc/domain/workbenchInteraction";
import type { HighlightDefect } from "@/features/sc/presentation/components/types";
import {
  usePerspectiveMapView,
  type MapBinRow,
  type MapViewport,
} from "@/features/sc/presentation/components/composables/usePerspectiveMapView";
import { usePerspectiveViewRef } from "@/features/sc/presentation/components/composables/usePerspectiveViewRef";
import { binsToDisplayArray } from "@/features/sc/presentation/components/transforms/binsToDisplayArrays";

const TABLE_COLUMNS = [
  "defect_id",
  "sample_id",
  "inspection_time",
  "wafer_key",
  "wafer_x",
  "wafer_y",
  "die_x",
  "die_y",
  "reticle_x",
  "reticle_y",
  "rough_bin",
  "class_number",
  "images",
  "test_id",
  "index_x",
  "index_y",
  "adder",
  "cluster_id",
  "size_x",
  "size_y",
  "size_d",
  "area",
  "final_bin",
  "manual_bin",
  "kill_ratio",
  "annotation_label",
  "prediction_label",
  "prediction_confidence",
  "final_class",
  "review_image_ids_json",
  "map_in_selection",
  "table_in_selection",
  "gallery_in_selection",
];

const PATCH_BLINK_COLUMNS = [
  "defect_id",
  "inspection_time",
  "wafer_key",
  "annotation_label",
  "prediction_label",
  "prediction_confidence",
];
const REVIEW_BLINK_COLUMNS = ["defect_id", "inspection_time", "wafer_key", "review_image_ids_json"];

const EMPTY_MAP_DISPLAY = new Float32Array(0);
const LARGE_SELECTION_THRESHOLD = 100;
const HIGHLIGHT_COLUMNS = [
  "defect_id",
  "wafer_x",
  "wafer_y",
  "die_x",
  "die_y",
  "reticle_x",
  "reticle_y",
];

const REVIEW_MODE_FILTER: Filter = ["images", ">", 0];
const GALLERY_SELECTION_FILTER: Filter = ["gallery_in_selection", "==", 1];

type SelectionMode = "none" | "small" | "large";
type MapMode = "wafer" | "die" | "reticle";

interface SelectionState {
  mode: SelectionMode;
  ids: number[];
}

interface SelectionUpdatePorts {
  map: number | null;
  table: number | null;
  gallery: number | null;
}

type SampleRowRecord = Record<string, PerspectiveScSampleItem>;

export type PerspectiveScSampleItem = ScSampleItem & {
  dieX: number;
  dieY: number;
  reticleX: number;
  reticleY: number;
  annotationLabel: string | null;
  predictionLabel: string | null;
  predictionConfidence: number | null;
};

function legendColumn(source: ScLegendSource | null | undefined): string {
  if (source === "bin") return "rough_bin";
  if (source === "annotation") return "annotation_label";
  if (source === "prediction") return "prediction_label";
  if (source === "final_class") return "final_class";
  return "class_number";
}

function numeric(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function stringOrNull(value: unknown): string | null {
  if (value == null || value === "") return null;
  return String(value);
}

function legendValue(value: unknown): string | number {
  if (value == null || value === "") return "__unlabeled__";
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const asNumber = Number(value);
  return Number.isFinite(asNumber) && String(value).trim() !== "" ? asNumber : String(value);
}

function legendKey(value: unknown): string {
  return String(legendValue(value));
}

function inspectionTimeToEpochMs(value: unknown): bigint {
  if (typeof value === "bigint") return value;
  if (typeof value === "number" && Number.isFinite(value)) return BigInt(Math.trunc(value));
  if (typeof value !== "string") return 0n;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? BigInt(parsed) : 0n;
}

function parseReviewImages(value: unknown): number[] {
  if (Array.isArray(value)) return value.map(Number).filter(Number.isFinite);
  if (typeof value !== "string" || value.length === 0) return [];
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.map(Number).filter(Number.isFinite);
  } catch {
    return [];
  }
}

function perspectiveField(field: string): string {
  if (field === "annotation_label") return "annotation_label";
  if (field === "prediction_label") return "prediction_label";
  if (field === "final_class") return "final_class";
  if (field === "class_number") return "class_number";
  return field;
}

function sampleFilterToPerspective(filter: ScSampleTableFilter | undefined): Filter[] {
  const out: Filter[] = [];
  for (const [field, raw] of Object.entries(filter ?? {})) {
    const col = perspectiveField(field);
    const sf = raw as {
      filterType: string;
      values?: Array<string | number>;
      type?: string;
      filter?: number;
      filterTo?: number;
    };
    if (sf.filterType === "set" && sf.values?.length) out.push([col, "in", sf.values] as Filter);
    if (
      sf.filterType === "number" &&
      sf.type === "inRange" &&
      typeof sf.filter === "number" &&
      typeof sf.filterTo === "number"
    ) {
      out.push([col, ">=", sf.filter] as Filter, [col, "<=", sf.filterTo] as Filter);
    }
  }
  return out;
}

function sortToPerspective(sort: ScSampleTableSort | null | undefined): [string, string][] {
  if (!sort?.direction) return [["defect_id", "asc"]];
  return [[perspectiveField(sort.field), sort.direction]];
}

function sortedUniqueIds(ids: unknown[]): number[] {
  return Array.from(new Set(ids.map(Number).filter(Number.isFinite))).sort((a, b) => a - b);
}

function emptySelection(): SelectionState {
  return { mode: "none", ids: [] };
}

function selectionStateFor(ids: number[]): SelectionState {
  if (ids.length === 0) return emptySelection();
  return {
    mode: ids.length > LARGE_SELECTION_THRESHOLD ? "large" : "small",
    ids,
  };
}

async function idsForFilter(table: Table, filters: Filter[]): Promise<number[]> {
  const v = await table.view({
    columns: ["defect_id"],
    filter: filters.length ? filters : undefined,
  } as never);
  try {
    const total = await v.num_rows();
    if (total === 0) return [];
    const limit = Math.min(total, 50_000);
    const data = (await v.to_columns({ start_row: 0, end_row: limit })) as Record<
      string,
      unknown[]
    >;
    return sortedUniqueIds(data.defect_id ?? []);
  } finally {
    try {
      await v.delete();
    } catch {
      /* best effort */
    }
  }
}

async function updateMapSelection(
  table: Table,
  defectIds: number[],
  mapVal: number,
  portId?: number | null,
): Promise<void> {
  if (defectIds.length === 0) return;
  await table.update(
    {
      defect_id: defectIds,
      map_in_selection: defectIds.map(() => mapVal),
    },
    portId == null ? undefined : { port_id: portId, format: null },
  );
}

async function replaceMapSelection(
  table: Table,
  previousIds: number[],
  nextIds: number[],
  portId?: number | null,
): Promise<void> {
  const nextSet = new Set(nextIds);
  const defectIds: number[] = [];
  const mapValues: number[] = [];
  for (const id of previousIds) {
    if (nextSet.has(id)) continue;
    defectIds.push(id);
    mapValues.push(0);
  }
  for (const id of nextIds) {
    defectIds.push(id);
    mapValues.push(1);
  }
  if (defectIds.length === 0) return;
  await table.update(
    {
      defect_id: defectIds,
      map_in_selection: mapValues,
    },
    portId == null ? undefined : { port_id: portId, format: null },
  );
}

async function updateTableSelection(
  table: Table,
  defectIds: number[],
  val: number,
  portId?: number | null,
): Promise<void> {
  if (defectIds.length === 0) return;
  await table.update(
    {
      defect_id: defectIds,
      table_in_selection: defectIds.map(() => val),
    },
    portId == null ? undefined : { port_id: portId, format: null },
  );
}

async function updateGallerySelection(
  table: Table,
  defectIds: number[],
  val: number,
  portId?: number | null,
): Promise<void> {
  if (defectIds.length === 0) return;
  await table.update(
    {
      defect_id: defectIds,
      gallery_in_selection: defectIds.map(() => val),
    },
    portId == null ? undefined : { port_id: portId, format: null },
  );
}

function rowsFromColumns(
  data: Record<string, unknown[]>,
  options: { includeReviewImages: boolean },
): PerspectiveScSampleItem[] {
  const ids = data.defect_id ?? [];
  return ids.map((id, i) => ({
    ...create(ScSampleItemSchema, {
      defectId: numeric(id),
      inspectionTime: inspectionTimeToEpochMs(data.inspection_time?.[i]),
      waferX: numeric(data.wafer_x?.[i]),
      waferY: numeric(data.wafer_y?.[i]),
      roughBin: numeric(data.rough_bin?.[i]),
      classNumber: numeric(data.class_number?.[i]),
      waferKey: numeric(data.wafer_key?.[i]),
      reviewImages: options.includeReviewImages
        ? parseReviewImages(data.review_image_ids_json?.[i]).map((imageId) =>
            create(ReviewImageSchema, { imageId }),
          )
        : [],
    }),
    dieX: numeric(data.die_x?.[i]),
    dieY: numeric(data.die_y?.[i]),
    reticleX: numeric(data.reticle_x?.[i]),
    reticleY: numeric(data.reticle_y?.[i]),
    annotationLabel: stringOrNull(data.annotation_label?.[i]),
    predictionLabel: stringOrNull(data.prediction_label?.[i]),
    predictionConfidence:
      data.prediction_confidence?.[i] == null ? null : numeric(data.prediction_confidence[i]),
  }));
}

async function jsonRowsForIds(
  table: Table,
  ids: number[],
  columns: string[],
  filters: Filter[],
  sort?: [string, string][],
  limit?: number,
): Promise<Array<Record<string, unknown>>> {
  if (ids.length === 0) return [];
  const v = await table.view({
    columns,
    filter: [...filters, ["defect_id", "in", ids] as Filter],
    sort,
  } as never);
  try {
    const rowCount = await v.num_rows();
    if (rowCount === 0) return [];
    return (await v.to_json({
      start_row: 0,
      end_row: limit == null ? rowCount : Math.min(rowCount, limit),
    })) as Array<Record<string, unknown>>;
  } finally {
    try {
      await v.delete();
    } catch {
      /* best effort */
    }
  }
}

async function highlightsForIds(table: Table, ids: number[]): Promise<HighlightDefect[]> {
  const defectIds = sortedUniqueIds(ids);
  if (defectIds.length === 0) return [];
  const rows = await jsonRowsForIds(
    table,
    defectIds,
    HIGHLIGHT_COLUMNS,
    [],
    [["defect_id", "asc"]],
  );
  return highlightsFromRows(rows);
}

function highlightsFromRows(rows: Array<Record<string, unknown>>): HighlightDefect[] {
  return rows.map((row) => ({
    defectId: numeric(row.defect_id),
    waferX: numeric(row.wafer_x),
    waferY: numeric(row.wafer_y),
    dieX: numeric(row.die_x),
    dieY: numeric(row.die_y),
    reticleX: numeric(row.reticle_x),
    reticleY: numeric(row.reticle_y),
  }));
}

function highlightsFromSamples(rows: PerspectiveScSampleItem[]): HighlightDefect[] {
  return rows.map((row) => ({
    defectId: Number(row.defectId),
    waferX: row.waferX,
    waferY: row.waferY,
    dieX: row.dieX,
    dieY: row.dieY,
    reticleX: row.reticleX,
    reticleY: row.reticleY,
  }));
}

function loadedRowsForIds(byId: SampleRowRecord, ids: number[]): PerspectiveScSampleItem[] {
  if (ids.length === 0) return [];
  return ids.flatMap((id) => {
    const row = byId[rowRecordKey(id)];
    return row ? [row] : [];
  });
}

function rowRecordKey(defectId: number): string {
  return `d:${defectId}`;
}

function rowsToRecord(rows: PerspectiveScSampleItem[]): SampleRowRecord {
  const byId: SampleRowRecord = {};
  for (const row of rows) {
    byId[rowRecordKey(Number(row.defectId))] = row;
  }
  return byId;
}

function coordForMode(row: HighlightDefect, mode: MapMode): { x: number; y: number } {
  switch (mode) {
    case "wafer":
      return { x: row.waferX, y: row.waferY };
    case "die":
      return { x: row.dieX, y: row.dieY };
    case "reticle":
      return { x: row.reticleX, y: row.reticleY };
  }
}

function binKey(gx: number, gy: number): string {
  return `${gx}:${gy}`;
}

function overlayGallerySelectionOnBins(
  rows: MapBinRow[] | null,
  highlights: HighlightDefect[],
  mode: MapMode,
): MapBinRow[] | null {
  if (!rows?.length || highlights.length === 0) return rows;
  const selectedBins = new Set<string>();
  for (const highlight of highlights) {
    const { x, y } = coordForMode(highlight, mode);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    const binSize = rows[0]?.binSize;
    if (!binSize) continue;
    selectedBins.add(binKey(Math.floor(x / binSize), Math.floor(y / binSize)));
  }
  if (selectedBins.size === 0) return rows;
  let changed = false;
  const nextRows = rows.map((row) => {
    if (!selectedBins.has(binKey(row.gx, row.gy)) || row.gallery_in_selection === 1) return row;
    changed = true;
    return { ...row, gallery_in_selection: 1 };
  });
  return changed ? nextRows : rows;
}

export function usePerspectiveInspectionModel(args: {
  table: Ref<Table | null>;
  inspectionTime?: Ref<string | undefined> | ComputedRef<string | undefined>;
  waferKey?: Ref<number | undefined> | ComputedRef<number | undefined>;
  legendGroupBy:
    | Ref<ScLegendSource | null | undefined>
    | ComputedRef<ScLegendSource | null | undefined>;
  tableFilter: Ref<ScSampleTableFilter | undefined> | ComputedRef<ScSampleTableFilter | undefined>;
  globalFilter?:
    | Ref<ScSampleTableFilter | undefined>
    | ComputedRef<ScSampleTableFilter | undefined>;
  tableSort?:
    | Ref<ScSampleTableSort | null | undefined>
    | ComputedRef<ScSampleTableSort | null | undefined>;
  zoom: Ref<MapViewport | null | undefined> | ComputedRef<MapViewport | null | undefined>;
  activeMapMode: Ref<"wafer" | "die" | "reticle"> | ComputedRef<"wafer" | "die" | "reticle">;
  galleryRandomSamplingFilter?: ComputedRef<Filter[]>;
}) {
  const hiddenLegendKeys = ref<string[]>([]);
  const canvasDims = ref({ w: 600, h: 600 });
  const mapSelection = ref<SelectionState>(emptySelection());
  const tableSelection = ref<SelectionState>(emptySelection());
  const gallerySelection = ref<SelectionState>(emptySelection());
  const tableSelectedDefectIds = ref<number[]>([]);
  const reviewMode = ref(false);
  const smallGalleryHighlights = ref<HighlightDefect[]>([]);
  const selectionUpdatePorts = ref<SelectionUpdatePorts>({
    map: null,
    table: null,
    gallery: null,
  });
  const tableRowRecord = ref<SampleRowRecord>({});
  const tableRows = computed(() => Object.values(tableRowRecord.value));
  const legendGroups = ref<Record<string, DefectList> | null>(null);
  const total = ref(0);

  const tableHeaderFilters = computed(() => sampleFilterToPerspective(args.tableFilter.value));
  const globalFilters = computed(() => sampleFilterToPerspective(args.globalFilter?.value));
  const reviewModeFilters = computed<Filter[]>(() =>
    reviewMode.value ? [REVIEW_MODE_FILTER] : [],
  );
  const samplesFilter = computed<Filter[]>(() => args.galleryRandomSamplingFilter?.value ?? []);

  // Simplified tableBaseFilters — no longer includes map selection;
  // map/table/gallery selections are handled by persistent views.
  const tableBaseFilters = computed<Filter[]>(() => [
    ...globalFilters.value,
    ...samplesFilter.value,
    ...reviewModeFilters.value,
  ]);
  const legendFilters = computed<Filter[]>(() => [
    ...globalFilters.value,
    ...samplesFilter.value,
    ...reviewModeFilters.value,
  ]);
  const legendCol = computed(() => legendColumn(args.legendGroupBy.value));
  const tableSort = computed(() => sortToPerspective(args.tableSort?.value));
  const zoomByMode = computed<Record<"wafer" | "die" | "reticle", MapViewport | null>>(() => ({
    wafer: args.zoom.value ?? null,
    die: args.zoom.value ?? null,
    reticle: args.zoom.value ?? null,
  }));
  const mapIgnoredUpdatePorts = computed<readonly number[]>(() =>
    selectionUpdatePorts.value.table == null ? [] : [selectionUpdatePorts.value.table],
  );

  let selectionPortTable: Table | null = null;

  async function ensureSelectionUpdatePorts(table: Table): Promise<SelectionUpdatePorts> {
    if (
      selectionPortTable === table &&
      selectionUpdatePorts.value.map != null &&
      selectionUpdatePorts.value.table != null &&
      selectionUpdatePorts.value.gallery != null
    ) {
      return selectionUpdatePorts.value;
    }
    selectionPortTable = table;
    const [mapPort, tablePort, galleryPort] = await Promise.all([
      table.make_port(),
      table.make_port(),
      table.make_port(),
    ]);
    if (args.table.value !== table) {
      return selectionUpdatePorts.value;
    }
    const ports = { map: mapPort, table: tablePort, gallery: galleryPort };
    selectionUpdatePorts.value = ports;
    return ports;
  }

  // Persistent view configs — each view has its own fixed filter set.
  // Selection filtering is done via data columns, not config rebuilding.
  const tableBaseConfig = computed(
    () =>
      ({
        columns: TABLE_COLUMNS,
        filter:
          tableHeaderFilters.value.length +
            globalFilters.value.length +
            samplesFilter.value.length +
            reviewModeFilters.value.length >
          0
            ? [
                ...tableHeaderFilters.value,
                ...globalFilters.value,
                ...samplesFilter.value,
                ...reviewModeFilters.value,
              ]
            : undefined,
        sort: tableSort.value,
      }) as ViewConfigUpdate,
  );

  const tableMapConfig = computed(
    () =>
      ({
        columns: TABLE_COLUMNS,
        filter: [...(tableBaseConfig.value.filter ?? []), ["map_in_selection", "==", 1] as Filter],
        sort: tableSort.value,
      }) as ViewConfigUpdate,
  );

  const blinkBaseFilters = computed<Filter[]>(() => [
    ...globalFilters.value,
    ...samplesFilter.value,
    ...reviewModeFilters.value,
  ]);
  const blinkSort = [["defect_id", "asc"]] as [string, string][];

  const blinkSelectionFilters = computed<Filter[]>(() => {
    if (tableSelection.value.mode === "small") {
      return [["defect_id", "in", tableSelection.value.ids] as Filter];
    }
    if (tableSelection.value.mode === "large") {
      return [["table_in_selection", "==", 1] as Filter];
    }
    if (mapSelection.value.mode === "small") {
      return [["defect_id", "in", mapSelection.value.ids] as Filter];
    }
    if (mapSelection.value.mode === "large") {
      return [["map_in_selection", "==", 1] as Filter];
    }
    return [];
  });

  const patchBlinkConfig = computed(
    () =>
      ({
        columns: PATCH_BLINK_COLUMNS,
        filter: [...blinkBaseFilters.value, ...blinkSelectionFilters.value].length
          ? [...blinkBaseFilters.value, ...blinkSelectionFilters.value]
          : undefined,
        sort: blinkSort,
      }) as ViewConfigUpdate,
  );

  const reviewBlinkBaseFilter = computed<Filter[]>(() => [
    ...globalFilters.value,
    ...samplesFilter.value,
    REVIEW_MODE_FILTER,
  ]);

  const reviewBlinkConfig = computed(
    () =>
      ({
        columns: REVIEW_BLINK_COLUMNS,
        filter: [...reviewBlinkBaseFilter.value, ...blinkSelectionFilters.value],
        sort: blinkSort,
      }) as ViewConfigUpdate,
  );

  const histConfig = computed(
    () =>
      ({
        columns: [legendCol.value],
        group_by: [legendCol.value],
        aggregates: { [legendCol.value]: "count" },
        filter: legendFilters.value.length ? legendFilters.value : undefined,
      }) as ViewConfigUpdate,
  );

  function sameHighlights(left: HighlightDefect[], right: HighlightDefect[]): boolean {
    if (left.length !== right.length) return false;
    for (let i = 0; i < left.length; i += 1) {
      const a = left[i];
      const b = right[i];
      if (
        a.defectId !== b.defectId ||
        a.waferX !== b.waferX ||
        a.waferY !== b.waferY ||
        a.dieX !== b.dieX ||
        a.dieY !== b.dieY ||
        a.reticleX !== b.reticleX ||
        a.reticleY !== b.reticleY
      ) {
        return false;
      }
    }
    return true;
  }

  function setSmallGalleryHighlights(next: HighlightDefect[]): void {
    if (sameHighlights(smallGalleryHighlights.value, next)) return;
    smallGalleryHighlights.value = next;
  }

  async function refreshSmallGalleryHighlights(): Promise<void> {
    if (gallerySelection.value.mode !== "small") {
      setSmallGalleryHighlights([]);
      return;
    }
    const table = args.table.value;
    if (!table) {
      setSmallGalleryHighlights([]);
      return;
    }
    setSmallGalleryHighlights(await highlightsForIds(table, gallerySelection.value.ids));
  }

  async function refreshTableData() {
    const mapView = mapSelection.value.mode !== "none" ? tableMapView.view.value : null;
    const globalView = tableGlobalView.view.value;
    const activeView = mapSelection.value.mode !== "none" ? mapView : globalView;
    if (!activeView) {
      total.value = 0;
      tableRowRecord.value = {};
      return;
    }
    const rowCount = await activeView.num_rows();
    total.value = rowCount;
    if (rowCount === 0) {
      tableRowRecord.value = {};
      return;
    }
    const data = (await activeView.to_columns({
      start_row: 0,
      end_row: Math.min(rowCount, 500),
    })) as Record<string, unknown[]>;
    tableRowRecord.value = rowsToRecord(rowsFromColumns(data, { includeReviewImages: true }));
  }

  // Persistent views live for the lifetime of the table and use selection flags
  // for large table/map selections.
  const tableGlobalView = usePerspectiveViewRef(args.table, tableBaseConfig, {
    onChange: refreshTableData,
  });
  const tableMapView = usePerspectiveViewRef(args.table, tableMapConfig, {
    onChange: refreshTableData,
  });
  const patchBlinkView = usePerspectiveViewRef(args.table, patchBlinkConfig);
  const reviewBlinkView = usePerspectiveViewRef(args.table, reviewBlinkConfig);
  const histView = usePerspectiveViewRef(args.table, histConfig);
  const sampleTableActiveView = computed<View | null>(() =>
    mapSelection.value.mode !== "none" && mapSelection.value.ids.length > 0
      ? tableMapView.view.value
      : null,
  );
  const sampleTableActiveViewConfig = computed<ViewConfigUpdate>(() =>
    mapSelection.value.mode !== "none" && mapSelection.value.ids.length > 0
      ? tableMapConfig.value
      : tableBaseConfig.value,
  );
  const sampleTableActiveViewConfigVersion = computed(() =>
    mapSelection.value.mode !== "none" && mapSelection.value.ids.length > 0
      ? tableMapView.version.value
      : tableGlobalView.version.value,
  );

  const map = usePerspectiveMapView(
    args.table,
    zoomByMode,
    globalFilters,
    hiddenLegendKeys,
    legendCol,
    canvasDims,
    ["wafer", "die", "reticle"],
    args.activeMapMode,
    mapIgnoredUpdatePorts,
  );

  async function syncLargeSelectionFlags(table: Table): Promise<void> {
    const ports = await ensureSelectionUpdatePorts(table);
    if (mapSelection.value.mode === "large") {
      await updateMapSelection(table, mapSelection.value.ids, 1, ports.map);
    }
    if (tableSelection.value.mode === "large") {
      await updateTableSelection(table, tableSelection.value.ids, 1, ports.table);
    }
    if (gallerySelection.value.mode === "large") {
      await updateGallerySelection(table, gallerySelection.value.ids, 1, ports.gallery);
    }
  }

  const waferDisplay = computed(() => {
    const rows = overlayGallerySelectionOnBins(
      map.waferRows.value,
      smallGalleryHighlights.value,
      "wafer",
    );
    const display = rows?.length ? binsToDisplayArray(rows, legendCol.value) : EMPTY_MAP_DISPLAY;
    return display;
  });
  const dieDisplay = computed(() => {
    const rows = overlayGallerySelectionOnBins(
      map.dieRows.value,
      smallGalleryHighlights.value,
      "die",
    );
    const display = rows?.length ? binsToDisplayArray(rows, legendCol.value) : EMPTY_MAP_DISPLAY;
    return display;
  });
  const reticleDisplay = computed(() => {
    const rows = overlayGallerySelectionOnBins(
      map.reticleRows.value,
      smallGalleryHighlights.value,
      "reticle",
    );
    const display = rows?.length ? binsToDisplayArray(rows, legendCol.value) : EMPTY_MAP_DISPLAY;
    return display;
  });
  const activeMapRowsReady = computed(() => {
    switch (args.activeMapMode.value) {
      case "wafer":
        return map.waferRows.value !== null;
      case "die":
        return map.dieRows.value !== null;
      case "reticle":
        return map.reticleRows.value !== null;
    }
    return false;
  });
  const activeMapLoading = computed(() => map.pending.value && !activeMapRowsReady.value);

  // Histogram watcher — unchanged logic, lock-free.
  watch(
    [() => histView.view.value, () => histView.version.value],
    async ([view]) => {
      if (!view) {
        legendGroups.value = null;
        return;
      }
      const current = view as View;
      const totalRows = await current.num_rows();
      if (histView.view.value !== current) return;
      if (totalRows === 0) {
        legendGroups.value = {};
        return;
      }
      const data = (await current.to_columns()) as Record<string, unknown[]>;
      if (histView.view.value !== current) return;
      const rowPaths = data.__ROW_PATH__ as unknown[][] | undefined;
      const counts = data[legendCol.value] as number[] | undefined;
      const groups: Record<string, DefectList> = {};
      for (let i = 0; i < (rowPaths?.length ?? 0); i += 1) {
        const path = rowPaths?.[i];
        if (!path || path.length === 0) continue;
        const key = legendKey(path[0]);
        groups[key] = create(DefectListSchema, {
          count: Number(counts?.[i] ?? 0),
          defectIds: [],
        });
      }
      legendGroups.value = groups;
    },
    { immediate: true },
  );

  // Initial data load: refresh when table first connects
  watch(
    () => args.table.value,
    async (tbl) => {
      if (tbl) {
        await syncLargeSelectionFlags(tbl);
        await refreshSmallGalleryHighlights();
        refreshTableData();
      } else {
        setSmallGalleryHighlights([]);
        selectionPortTable = null;
        selectionUpdatePorts.value = { map: null, table: null, gallery: null };
      }
    },
  );

  watch(
    [() => globalFilters.value, () => reviewMode.value],
    () => {
      void refreshSmallGalleryHighlights();
    },
    { deep: true },
  );

  async function queryBoxSelection(
    mode: "wafer" | "die" | "reticle",
    region: { x: number; y: number; w: number; h: number },
  ): Promise<number[]> {
    const table = args.table.value;
    if (!table) return [];
    const filters = [...globalFilters.value];
    if (region.w > 1 && region.h > 1) {
      filters.push(
        [`${mode}_x`, ">=", region.x] as Filter,
        [`${mode}_x`, "<=", region.x + region.w] as Filter,
        [`${mode}_y`, ">=", region.y] as Filter,
        [`${mode}_y`, "<=", region.y + region.h] as Filter,
      );
    }
    return idsForFilter(table, filters);
  }

  async function queryLegendSelection(key: string | number): Promise<number[]> {
    const table = args.table.value;
    if (!table) return [];
    const col = legendCol.value;
    if (String(key) === "__unlabeled__") {
      const unlabeledFilter: Filter = [col, "is null", null];
      return idsForFilter(table, [...globalFilters.value, unlabeledFilter]);
    }
    const value = col === "class_number" || col === "rough_bin" ? numeric(key) : String(key);
    return idsForFilter(table, [...globalFilters.value, [col, "==", value] as Filter]);
  }

  async function applyMapSelection(ids: number[]): Promise<void> {
    const table = args.table.value;
    if (!table) return;
    const next = selectionStateFor(sortedUniqueIds(ids));
    const needsTableUpdate = mapSelection.value.mode !== "none" || next.mode !== "none";
    const ports = needsTableUpdate ? await ensureSelectionUpdatePorts(table) : null;
    const previous = mapSelection.value;
    mapSelection.value = next;
    if (needsTableUpdate) {
      await replaceMapSelection(table, previous.ids, next.ids, ports?.map);
    }
    if (next.mode === "none") refreshTableData();
  }

  async function appendMapSelection(ids: number[]): Promise<number[]> {
    const nextIds = sortedUniqueIds([...mapSelection.value.ids, ...ids]);
    await applyMapSelection(nextIds);
    return nextIds;
  }

  async function clearMapSelection(): Promise<void> {
    await applyMapSelection([]);
  }

  function setHiddenLegendKeys(keys: string[]): void {
    hiddenLegendKeys.value = keys;
  }

  async function setTableSelectedDefectIds(ids: number[]): Promise<void> {
    const table = args.table.value;
    const nextIds = sortedUniqueIds(ids);
    if (!table) {
      tableSelectedDefectIds.value = nextIds;
      tableSelection.value = selectionStateFor(nextIds);
      return;
    }
    const next = selectionStateFor(nextIds);
    const needsTableUpdate = tableSelection.value.mode === "large" || next.mode === "large";
    const ports = needsTableUpdate ? await ensureSelectionUpdatePorts(table) : null;
    if (tableSelection.value.mode === "large") {
      await updateTableSelection(table, tableSelection.value.ids, 0, ports?.table);
    }
    tableSelection.value = next;
    tableSelectedDefectIds.value = next.ids;
    if (next.mode === "large") {
      await updateTableSelection(table, next.ids, 1, ports?.table);
    }
  }

  async function setGallerySelectedDefectIds(ids: Array<number | string>): Promise<void> {
    const numericIds = sortedUniqueIds(ids);
    const table = args.table.value;
    if (!table) {
      gallerySelection.value = selectionStateFor(numericIds);
      setSmallGalleryHighlights([]);
      return;
    }
    const next = selectionStateFor(numericIds);
    const needsTableUpdate = gallerySelection.value.mode === "large" || next.mode === "large";
    const ports = needsTableUpdate ? await ensureSelectionUpdatePorts(table) : null;
    if (gallerySelection.value.mode === "large") {
      await updateGallerySelection(table, gallerySelection.value.ids, 0, ports?.gallery);
    }
    gallerySelection.value = next;
    if (next.mode === "large") {
      setSmallGalleryHighlights([]);
      await updateGallerySelection(table, next.ids, 1, ports?.gallery);
    } else {
      await refreshSmallGalleryHighlights();
    }
  }

  function setReviewMode(value: boolean): void {
    reviewMode.value = value;
  }

  async function highlightDefectsFor(): Promise<HighlightDefect[]> {
    const table = args.table.value;
    if (!table) return [];
    if (gallerySelection.value.mode === "small") {
      return highlightsForIds(table, gallerySelection.value.ids);
    }
    const v = await table.view({
      columns: HIGHLIGHT_COLUMNS,
      filter: [GALLERY_SELECTION_FILTER],
    } as never);
    try {
      const totalRows = await v.num_rows();
      if (totalRows === 0) return [];
      const data = (await v.to_json()) as Array<Record<string, unknown>>;
      return highlightsFromRows(data);
    } finally {
      try {
        await v.delete();
      } catch {
        /* best effort */
      }
    }
  }

  const blinkFetching = computed(
    () => patchBlinkView.pending.value || reviewBlinkView.pending.value,
  );

  async function loadGlobalDistinctValues(
    field: string,
    search: string,
  ): Promise<Array<string | number>> {
    const table = args.table.value;
    if (!table) return [];
    const col = perspectiveField(field);
    const filters = search.trim() ? [[col, "contains", search.trim()] satisfies Filter] : [];
    const v = await table.view({
      columns: [col],
      group_by: [col],
      aggregates: { [col]: "count" },
      filter: filters.length ? filters : undefined,
    } as never);
    try {
      const totalRows = await v.num_rows();
      if (totalRows === 0) return [];
      const data = (await v.to_columns({
        start_row: 0,
        end_row: Math.min(totalRows, 500),
      })) as Record<string, unknown[]>;
      const rowPaths = data.__ROW_PATH__ as unknown[][] | undefined;
      return (rowPaths ?? [])
        .filter((path) => path && path.length > 0)
        .map((path) => legendValue(path[0]))
        .filter(
          (value): value is string | number =>
            typeof value === "string" || typeof value === "number",
        );
    } finally {
      try {
        await v.delete();
      } catch {
        /* best effort */
      }
    }
  }

  async function highlightDefectsForIds(ids: number[]): Promise<HighlightDefect[]> {
    const table = args.table.value;
    if (!table) return [];
    return highlightsForIds(table, ids);
  }

  return {
    waferDisplay,
    dieDisplay,
    reticleDisplay,
    legendGroups,
    samples: tableRows,
    patchBlinkView: patchBlinkView.view,
    patchBlinkViewVersion: patchBlinkView.version,
    reviewBlinkView: reviewBlinkView.view,
    reviewBlinkViewVersion: reviewBlinkView.version,
    blinkFetching,
    tableBaseFilters,
    sampleTableActiveView,
    sampleTableActiveViewVersion: tableMapView.version,
    sampleTableActiveViewConfig,
    sampleTableActiveViewConfigVersion,
    total,
    mapLoading: map.pending,
    activeMapLoading,
    mapError: map.error,
    tableLoading: tableGlobalView.pending,
    tableSelectedDefectIds,
    loadGlobalDistinctValues,
    setTableSelectedDefectIds,
    setGallerySelectedDefectIds,
    setReviewMode,
    queryBoxSelection,
    queryLegendSelection,
    applyMapSelection,
    appendMapSelection,
    clearMapSelection,
    setHiddenLegendKeys,
    highlightDefectsFor,
    highlightDefectsForIds,
  };
}
