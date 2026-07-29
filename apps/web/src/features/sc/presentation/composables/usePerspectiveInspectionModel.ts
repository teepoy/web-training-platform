import { computed, ref, watch, type ComputedRef, type Ref } from "vue";
import { create } from "@bufbuild/protobuf";
import type { Filter, ViewConfigUpdate } from "@perspective-dev/client";
import type { DefectList } from "@/features/sc/generated/proto/sc/v1/sample_pb";
import { DefectListSchema } from "@/features/sc/generated/proto/sc/v1/sample_pb";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type { ScLegendSource } from "@/features/sc/domain/workbenchInteraction";
import type { HighlightDefect } from "@/features/sc/presentation/components/types";
import { usePerspectiveMapView } from "@/features/sc/presentation/components/composables/usePerspectiveMapView";
import {
  useManagedPerspectiveView,
  type PerspectiveViewSnapshot,
} from "@/features/sc/presentation/components/composables/useManagedPerspectiveView";
import { managePerspectiveTable } from "@/features/sc/presentation/composables/managedPerspectiveView";
import type { ScPerspectiveTable as Table } from "./perspectiveWorkerClient";
import { perspectiveViewConfigKey } from "./perspectiveViewConfig";
import { buildPerspectiveFilters, perspectiveFilterField } from "./perspectiveFilter";
import type { PerspectiveExpressions } from "./perspectiveReticleExpressions";
import { buildPerspectiveSampleViewConfig } from "./perspectiveSampleViewConfig";

const PATCH_GALLERY_COLUMNS = [
  "defect_id",
  "annotation_label",
  "prediction_label",
  "prediction_confidence",
];
const REVIEW_GALLERY_COLUMNS = [
  "sample_id",
  "defect_id",
  "review_image_ids_json",
  "annotation_label",
  "prediction_label",
  "prediction_confidence",
];

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
type MapMode = "wafer" | "die" | "reticle";

interface SelectionState {
  ids: number[];
}

interface SelectionUpdatePorts {
  map: number | null;
  table: number | null;
}

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

function legendValue(value: unknown): string | number {
  if (value == null || value === "") return "__unlabeled__";
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const asNumber = Number(value);
  return Number.isFinite(asNumber) && String(value).trim() !== "" ? asNumber : String(value);
}

function legendKey(value: unknown): string {
  return String(legendValue(value));
}

function sortedUniqueIds(ids: unknown[]): number[] {
  return Array.from(new Set(ids.map(Number).filter(Number.isFinite))).sort((a, b) => a - b);
}

function emptySelection(): SelectionState {
  return { ids: [] };
}

function selectionStateFor(ids: number[]): SelectionState {
  return ids.length === 0 ? emptySelection() : { ids };
}

async function idsForFilter(
  table: Table,
  filters: Filter[],
  expressions?: PerspectiveExpressions,
): Promise<number[]> {
  const managedTable = managePerspectiveTable(table);
  const managed = await managedTable.view({
    columns: ["defect_id"],
    expressions,
    filter: filters.length ? filters : undefined,
  } as never);
  try {
    const total = await managed.num_rows();
    if (total === 0) return [];
    const limit = total;
    const data = (await managed.to_columns({ start_row: 0, end_row: limit })) as Record<
      string,
      unknown[]
    >;
    return sortedUniqueIds(data.defect_id ?? []);
  } finally {
    managed.retire();
  }
}

async function updateMapSelection(
  table: Table,
  defectIds: number[],
  mapVal: number,
  portId?: number | null,
): Promise<void> {
  if (defectIds.length === 0) return;
  await managePerspectiveTable(table).update(
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
  await managePerspectiveTable(table).update(
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
  await managePerspectiveTable(table).update(
    {
      defect_id: defectIds,
      table_in_selection: defectIds.map(() => val),
    },
    portId == null ? undefined : { port_id: portId, format: null },
  );
}

async function replaceTableSelection(
  table: Table,
  previousIds: number[],
  nextIds: number[],
  portId?: number | null,
): Promise<void> {
  const previousSet = new Set(previousIds);
  const nextSet = new Set(nextIds);
  const defectIds: number[] = [];
  const tableValues: number[] = [];
  for (const id of previousIds) {
    if (nextSet.has(id)) continue;
    defectIds.push(id);
    tableValues.push(0);
  }
  for (const id of nextIds) {
    if (previousSet.has(id)) continue;
    defectIds.push(id);
    tableValues.push(1);
  }
  if (defectIds.length === 0) return;
  await managePerspectiveTable(table).update(
    {
      defect_id: defectIds,
      table_in_selection: tableValues,
    },
    portId == null ? undefined : { port_id: portId, format: null },
  );
}

async function jsonRowsForIds(
  table: Table,
  ids: number[],
  columns: string[],
  filters: Filter[],
  sort?: [string, string][],
  limit?: number,
  expressions?: PerspectiveExpressions,
): Promise<Array<Record<string, unknown>>> {
  if (ids.length === 0) return [];
  const managedTable = managePerspectiveTable(table);
  const managed = await managedTable.view({
    columns,
    expressions,
    filter: [...filters, ["defect_id", "in", ids] as Filter],
    sort,
  } as never);
  try {
    const rowCount = await managed.num_rows();
    if (rowCount === 0) return [];
    return (await managed.to_json({
      start_row: 0,
      end_row: limit == null ? rowCount : Math.min(rowCount, limit),
    })) as Array<Record<string, unknown>>;
  } finally {
    managed.retire();
  }
}

async function highlightsForIds(
  table: Table,
  ids: number[],
  expressions: PerspectiveExpressions,
): Promise<HighlightDefect[]> {
  const defectIds = sortedUniqueIds(ids);
  if (defectIds.length === 0) return [];
  const rows = await jsonRowsForIds(
    table,
    defectIds,
    HIGHLIGHT_COLUMNS,
    [],
    [["defect_id", "asc"]],
    undefined,
    expressions,
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

export function usePerspectiveInspectionModel(args: {
  perspectiveTable: Ref<Table | null>;
  legendGroupBy:
    | Ref<ScLegendSource | null | undefined>
    | ComputedRef<ScLegendSource | null | undefined>;
  globalFilter?:
    | Ref<ScSampleTableFilter | undefined>
    | ComputedRef<ScSampleTableFilter | undefined>;
  tableFilter?: Ref<ScSampleTableFilter | undefined> | ComputedRef<ScSampleTableFilter | undefined>;
  tableSort?:
    | Ref<ScSampleTableSort | null | undefined>
    | ComputedRef<ScSampleTableSort | null | undefined>;
  reticleExpressions: Ref<PerspectiveExpressions> | ComputedRef<PerspectiveExpressions>;
  galleryRandomSamplingFilter?: ComputedRef<Filter[]>;
  onRecoverableError?: (reason: string, err: unknown) => void;
}) {
  const mapSelection = ref<SelectionState>(emptySelection());
  const tableSelection = ref<SelectionState>(emptySelection());
  const tableSelectedDefectIds = ref<number[]>([]);
  const mapSelectedDefectIds = computed(() => mapSelection.value.ids);
  const reviewMode = ref(false);
  const selectionUpdatePorts = ref<SelectionUpdatePorts>({
    map: null,
    table: null,
  });
  const selectionUpdatePortIds = computed(() =>
    [selectionUpdatePorts.value.map, selectionUpdatePorts.value.table].filter(
      (portId): portId is number => portId != null,
    ),
  );
  const legendGroups = ref<Record<string, DefectList> | null>(null);

  const globalFilters = computed(() => buildPerspectiveFilters(args.globalFilter?.value));
  const reviewModeFilters = computed<Filter[]>(() =>
    reviewMode.value ? [REVIEW_MODE_FILTER] : [],
  );
  const samplesFilter = computed<Filter[]>(() => args.galleryRandomSamplingFilter?.value ?? []);

  const tableBaseFilters = computed<Filter[]>(() => {
    const filters = [...globalFilters.value, ...samplesFilter.value, ...reviewModeFilters.value];
    if (mapSelection.value.ids.length > 0) {
      filters.push(["map_in_selection", "==", 1] as Filter);
    }
    return filters;
  });
  const legendFilters = computed<Filter[]>(() => [
    ...globalFilters.value,
    ...samplesFilter.value,
    ...reviewModeFilters.value,
  ]);
  const legendCol = computed(() => legendColumn(args.legendGroupBy.value));

  let selectionPortTable: Table | null = null;

  async function ensureSelectionUpdatePorts(table: Table): Promise<SelectionUpdatePorts> {
    if (
      selectionPortTable === table &&
      selectionUpdatePorts.value.map != null &&
      selectionUpdatePorts.value.table != null
    ) {
      return selectionUpdatePorts.value;
    }
    selectionPortTable = table;
    const managedTable = managePerspectiveTable(table);
    const [mapPort, tablePort] = await Promise.all([
      managedTable.make_port(),
      managedTable.make_port(),
    ]);
    if (args.perspectiveTable.value !== table) {
      return selectionUpdatePorts.value;
    }
    const ports = { map: mapPort, table: tablePort };
    selectionUpdatePorts.value = ports;
    return ports;
  }

  const sampleTableBaseViewConfig = computed<ViewConfigUpdate>(() => ({
    expressions: args.reticleExpressions.value,
    filter: tableBaseFilters.value.length ? tableBaseFilters.value : undefined,
  }));

  const gallerySelectionFilters = computed<Filter[]>(() => {
    return tableSelection.value.ids.length > 0 ? [["table_in_selection", "==", 1] as Filter] : [];
  });

  const patchGalleryViewConfig = computed<ViewConfigUpdate>(() =>
    buildPerspectiveSampleViewConfig({
      base: {
        columns: PATCH_GALLERY_COLUMNS,
        filter: tableBaseFilters.value,
      },
      tableFilter: args.tableFilter?.value,
      tableSort: args.tableSort?.value,
      additionalFilters: gallerySelectionFilters.value,
    }),
  );

  const reviewGalleryViewConfig = computed<ViewConfigUpdate>(() =>
    buildPerspectiveSampleViewConfig({
      base: {
        columns: REVIEW_GALLERY_COLUMNS,
        filter: tableBaseFilters.value,
      },
      tableFilter: args.tableFilter?.value,
      tableSort: args.tableSort?.value,
      additionalFilters: gallerySelectionFilters.value,
    }),
  );
  const activeGalleryMode = computed<"patch" | "review">(() =>
    reviewMode.value ? "review" : "patch",
  );
  const activeGalleryViewConfig = computed<ViewConfigUpdate>(() =>
    activeGalleryMode.value === "review"
      ? reviewGalleryViewConfig.value
      : patchGalleryViewConfig.value,
  );

  const histogramViewConfig = computed(
    () =>
      ({
        columns: [legendCol.value],
        group_by: [legendCol.value],
        aggregates: { [legendCol.value]: "count" },
        filter: legendFilters.value.length ? legendFilters.value : undefined,
      }) as ViewConfigUpdate,
  );

  const galleryViewState = useManagedPerspectiveView(
    args.perspectiveTable,
    activeGalleryViewConfig,
    {
      onRecoverableError: args.onRecoverableError,
    },
  );
  const patchGalleryViewSnapshot = computed<PerspectiveViewSnapshot | null>(() => {
    const snapshot = galleryViewState.snapshot.value;
    if (
      activeGalleryMode.value !== "patch" ||
      snapshot?.viewConfigKey !== perspectiveViewConfigKey(patchGalleryViewConfig.value)
    ) {
      return null;
    }
    return snapshot;
  });
  const reviewGalleryViewSnapshot = computed<PerspectiveViewSnapshot | null>(() => {
    const snapshot = galleryViewState.snapshot.value;
    if (
      activeGalleryMode.value !== "review" ||
      snapshot?.viewConfigKey !== perspectiveViewConfigKey(reviewGalleryViewConfig.value)
    ) {
      return null;
    }
    return snapshot;
  });
  const histogramViewState = useManagedPerspectiveView(args.perspectiveTable, histogramViewConfig, {
    onRecoverableError: args.onRecoverableError,
  });
  const map = usePerspectiveMapView(
    args.perspectiveTable,
    globalFilters,
    legendCol,
    args.reticleExpressions,
    args.onRecoverableError,
  );
  let tableSelectionUpdateQueue = Promise.resolve();

  async function syncSelectionFlags(table: Table): Promise<void> {
    if (mapSelection.value.ids.length === 0 && tableSelection.value.ids.length === 0) return;
    const ports = await ensureSelectionUpdatePorts(table);
    if (mapSelection.value.ids.length > 0) {
      await updateMapSelection(table, mapSelection.value.ids, 1, ports.map);
    }
    if (tableSelection.value.ids.length > 0) {
      await updateTableSelection(table, tableSelection.value.ids, 1, ports.table);
    }
  }

  const activeMapLoading = computed(() => map.pending.value || map.arrowData.value === null);

  // A new snapshot is published for both View replacement and in-place data updates.
  watch(
    () => histogramViewState.snapshot.value,
    async (snapshot) => {
      try {
        if (!snapshot) {
          legendGroups.value = null;
          return;
        }
        const currentSnapshot = snapshot;
        const totalRows = await snapshot.view.num_rows();
        if (histogramViewState.snapshot.value !== currentSnapshot) return;
        if (totalRows === 0) {
          legendGroups.value = {};
          return;
        }
        const data = (await snapshot.view.to_columns()) as Record<string, unknown[]>;
        if (histogramViewState.snapshot.value !== currentSnapshot) return;
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
      } catch (err) {
        args.onRecoverableError?.("histogram view update failed", err);
      }
    },
    { immediate: true },
  );

  // Initial data load: refresh when table first connects
  watch(
    () => args.perspectiveTable.value,
    async (tbl) => {
      if (tbl) {
        await syncSelectionFlags(tbl);
      } else {
        selectionPortTable = null;
        selectionUpdatePorts.value = { map: null, table: null };
      }
    },
  );

  async function queryBoxSelection(
    mode: "wafer" | "die" | "reticle",
    region: { x: number; y: number; w: number; h: number },
  ): Promise<number[]> {
    const table = args.perspectiveTable.value;
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
    return idsForFilter(
      table,
      filters,
      mode === "reticle" ? args.reticleExpressions.value : undefined,
    );
  }

  async function queryLegendSelection(key: string | number): Promise<number[]> {
    const table = args.perspectiveTable.value;
    if (!table) return [];
    const col = legendCol.value;
    if (String(key) === "__unlabeled__") {
      const unlabeledFilter: Filter = [col, "is null", null];
      return idsForFilter(table, [...globalFilters.value, unlabeledFilter]);
    }
    const value = col === "class_number" || col === "rough_bin" ? numeric(key) : String(key);
    return idsForFilter(table, [...globalFilters.value, [col, "==", value] as Filter]);
  }

  async function queryGlobalFilterCount(): Promise<number> {
    const table = args.perspectiveTable.value;
    if (!table) {
      throw new Error("Perspective data is not ready");
    }
    const managed = await managePerspectiveTable(table).view({
      columns: ["defect_id"],
      filter: globalFilters.value.length ? globalFilters.value : undefined,
    } as never);
    try {
      return await managed.num_rows();
    } finally {
      managed.retire();
    }
  }

  async function queryRandomGlobalFilteredDefectIds(count: number): Promise<number[]> {
    if (!Number.isInteger(count) || count <= 0) {
      throw new Error("Sampling count must be a positive integer");
    }
    const table = args.perspectiveTable.value;
    if (!table) {
      throw new Error("Perspective data is not ready");
    }
    const managed = await managePerspectiveTable(table).view({
      columns: ["defect_id"],
      filter: globalFilters.value.length ? globalFilters.value : undefined,
    } as never);
    try {
      const total = await managed.num_rows();
      if (total === 0) return [];
      const data = (await managed.to_columns({
        start_row: 0,
        end_row: total,
      })) as Record<string, unknown[]>;
      const defectIds = (data.defect_id ?? []).map(Number).filter(Number.isFinite);
      const sampleSize = Math.min(count, defectIds.length);
      for (let index = 0; index < sampleSize; index += 1) {
        const swapIndex = index + Math.floor(Math.random() * (defectIds.length - index));
        [defectIds[index], defectIds[swapIndex]] = [defectIds[swapIndex], defectIds[index]];
      }
      return defectIds.slice(0, sampleSize);
    } finally {
      managed.retire();
    }
  }

  async function applyMapSelection(ids: number[]): Promise<void> {
    const table = args.perspectiveTable.value;
    if (!table) return;
    const next = selectionStateFor(sortedUniqueIds(ids));
    const needsTableUpdate = mapSelection.value.ids.length > 0 || next.ids.length > 0;
    const ports = needsTableUpdate ? await ensureSelectionUpdatePorts(table) : null;
    const previous = mapSelection.value;
    if (needsTableUpdate) {
      await replaceMapSelection(table, previous.ids, next.ids, ports?.map);
    }
    mapSelection.value = next;
  }

  async function appendMapSelection(ids: number[]): Promise<number[]> {
    const nextIds = sortedUniqueIds([...mapSelection.value.ids, ...ids]);
    await applyMapSelection(nextIds);
    return nextIds;
  }

  async function clearMapSelection(): Promise<void> {
    await applyMapSelection([]);
  }

  async function applyTableSelection(ids: number[]): Promise<void> {
    const table = args.perspectiveTable.value;
    if (!table) {
      tableSelectedDefectIds.value = ids;
      tableSelection.value = selectionStateFor(ids);
      return;
    }
    const next = selectionStateFor(ids);
    const previous = tableSelection.value;
    const needsTableUpdate = previous.ids.length > 0 || next.ids.length > 0;
    const ports = needsTableUpdate ? await ensureSelectionUpdatePorts(table) : null;
    if (needsTableUpdate) {
      await replaceTableSelection(table, previous.ids, next.ids, ports?.table);
    }
    tableSelection.value = next;
    tableSelectedDefectIds.value = next.ids;
  }

  function setTableSelectedDefectIds(ids: number[]): Promise<void> {
    const nextIds = sortedUniqueIds(ids);
    tableSelectionUpdateQueue = tableSelectionUpdateQueue
      .then(() => applyTableSelection(nextIds))
      .catch((error: unknown) => {
        args.onRecoverableError?.("table selection update failed", error);
      });
    return tableSelectionUpdateQueue;
  }

  function setReviewMode(value: boolean): void {
    reviewMode.value = value;
  }

  const galleryLoading = computed(() => galleryViewState.isPending.value);

  async function loadGlobalDistinctValues(
    field: string,
    search: string,
  ): Promise<Array<string | number>> {
    const table = args.perspectiveTable.value;
    if (!table) return [];
    const col = perspectiveFilterField(field);
    const filters = search.trim() ? [[col, "contains", search.trim()] satisfies Filter] : [];
    const managedTable = managePerspectiveTable(table);
    const managed = await managedTable.view({
      columns: [col],
      group_by: [col],
      aggregates: { [col]: "count" },
      filter: filters.length ? filters : undefined,
    } as never);
    try {
      const totalRows = await managed.num_rows();
      if (totalRows === 0) return [];
      const data = (await managed.to_columns({
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
      managed.retire();
    }
  }

  async function highlightDefectsForIds(ids: number[]): Promise<HighlightDefect[]> {
    const table = args.perspectiveTable.value;
    if (!table) return [];
    return highlightsForIds(table, ids, args.reticleExpressions.value);
  }

  return {
    mapArrowData: map.arrowData,
    mapLegendColumn: legendCol,
    legendGroups,
    patchGalleryViewSnapshot,
    reviewGalleryViewSnapshot,
    galleryLoading,
    sampleTableBaseViewConfig,
    mapLoading: map.pending,
    activeMapLoading,
    mapError: map.error,
    mapProgressMessage: map.progressMessage,
    mapProgressPercent: map.progressPercent,
    mapSelectedDefectIds,
    tableSelectedDefectIds,
    selectionUpdatePortIds,
    loadGlobalDistinctValues,
    setTableSelectedDefectIds,
    setReviewMode,
    queryBoxSelection,
    queryLegendSelection,
    queryGlobalFilterCount,
    queryRandomGlobalFilteredDefectIds,
    applyMapSelection,
    appendMapSelection,
    clearMapSelection,
    highlightDefectsForIds,
  };
}
