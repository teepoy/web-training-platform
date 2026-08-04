import { create } from "@bufbuild/protobuf";
import { computed, onScopeDispose, ref, watch, type ComputedRef, type Ref } from "vue";
import type { DefectList } from "@/features/sc/generated/proto/sc/v1/sample_pb";
import { DefectListSchema } from "@/features/sc/generated/proto/sc/v1/sample_pb";
import { buildScDataFilters } from "@/features/sc/application/workbenchDataFilter";
import { isScMissingFilterValue } from "@/features/sc/domain/missingFilterValue";
import type { ReticleMapOptions } from "@/features/sc/application/reticleMapOptions";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type {
  ScDataFilter,
  ScGalleryDataQuery,
  ScReticleProjection,
  ScTableSelectionConstraint,
  ScWorkbenchDataSource,
} from "@/features/sc/domain/workbenchDataSource";
import type {
  ScLegendSource,
  ScMapSelectionMode,
  ScSampleTableDataSource,
} from "@/features/sc/domain/workbenchInteraction";
import type { ScMapLassoSelection } from "@platform/sc-map-element";

interface IdSelectionState {
  ids: number[];
}

interface MapSelectionFilterState extends IdSelectionState {
  mode: ScMapSelectionMode;
}

export interface ScSamplingCandidateOptions {
  reviewOnly: boolean;
  mapSelectionOnly: boolean;
}

function sortedUniqueIds(ids: readonly number[]): number[] {
  return [...new Set(ids.filter(Number.isFinite))].sort((left, right) => left - right);
}

function legendColumn(source: ScLegendSource | null | undefined): string {
  if (source === "bin") return "rough_bin";
  if (source === "annotation") return "annotation_label";
  if (source === "prediction") return "prediction_label";
  if (source === "final_class") return "final_class";
  return "class_number";
}

function transferableBuffer(value: Uint8Array): ArrayBuffer {
  return value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength) as ArrayBuffer;
}

export function useSqlInspectionModel(args: {
  dataSource: Ref<ScWorkbenchDataSource | null> | ComputedRef<ScWorkbenchDataSource | null>;
  legendGroupBy: ComputedRef<ScLegendSource | null | undefined>;
  globalFilter: ComputedRef<ScSampleTableFilter>;
  tableFilter: ComputedRef<ScSampleTableFilter | undefined>;
  tableSort: ComputedRef<ScSampleTableSort | null | undefined>;
  reticle: ComputedRef<ScReticleProjection>;
  galleryRandomSamplingDefectIds: ComputedRef<Set<string> | undefined>;
  onRecoverableError?: (reason: string, error: unknown) => void;
}) {
  const mapArrowData = ref<ArrayBuffer[] | null>(null);
  const mapLoading = ref(false);
  const mapError = ref<string | null>(null);
  const mapProgressMessage = ref("Waiting for map data");
  const mapProgressPercent = ref(0);
  const legendGroups = ref<Record<string, DefectList> | null>(null);
  const mapSelection = ref<IdSelectionState>({ ids: [] });
  const mapSelectionFilter = ref<MapSelectionFilterState | null>(null);
  const mapSelectionFilterHistory = ref<Array<MapSelectionFilterState | null>>([]);
  const mapSelectionMode = computed(() => mapSelectionFilter.value?.mode ?? null);
  const canUndoMapSelectionMode = computed(() => mapSelectionFilterHistory.value.length > 0);
  const tableSelection = ref<ScTableSelectionConstraint>({ kind: "ids", ids: [] });
  const mapSelectedDefectIds = computed(() => mapSelection.value.ids);
  const reviewMode = ref(false);
  const invalidationRevision = ref(0);
  let mapLoadSequence = 0;
  let aggregateLoadSequence = 0;
  let unsubscribe: (() => void) | null = null;

  const mapLegendColumn = computed(() => legendColumn(args.legendGroupBy.value));
  const globalFilters = computed(() => buildScDataFilters(args.globalFilter.value));
  const randomSamplingFilters = computed<ScDataFilter[]>(() => {
    const ids = args.galleryRandomSamplingDefectIds.value;
    return ids?.size ? [["defect_id", "in", [...ids].map(Number)]] : [];
  });
  const reviewFilters = computed<ScDataFilter[]>(() =>
    reviewMode.value ? [["images", ">", 0]] : [],
  );
  const tableBaseFilters = computed<ScDataFilter[]>(() => [
    ...globalFilters.value,
    ...randomSamplingFilters.value,
    ...reviewFilters.value,
    ...(mapSelectionFilter.value
      ? ([
          [
            "defect_id",
            mapSelectionFilter.value.mode === "include" ? "in" : "not in",
            mapSelectionFilter.value.ids,
          ],
        ] as ScDataFilter[])
      : []),
  ]);
  const aggregateFilters = computed<ScDataFilter[]>(() => [
    ...globalFilters.value,
    ...randomSamplingFilters.value,
    ...reviewFilters.value,
  ]);

  function samplingCandidateFilters(options: ScSamplingCandidateOptions): ScDataFilter[] {
    if (options.mapSelectionOnly && mapSelection.value.ids.length === 0) {
      throw new Error("Current map selection is empty");
    }
    return [
      ...globalFilters.value,
      ...(options.reviewOnly ? ([["images", ">", 0]] as ScDataFilter[]) : []),
      ...(options.mapSelectionOnly
        ? ([["defect_id", "in", mapSelection.value.ids]] as ScDataFilter[])
        : []),
    ];
  }

  const sampleTableDataSource = computed<ScSampleTableDataSource | undefined>(() => {
    const source = args.dataSource.value;
    if (!source) return undefined;
    const filters = tableBaseFilters.value;
    const reticle = args.reticle.value;
    return {
      scopeKey: `${source.scopeKey}:${JSON.stringify(filters)}:${JSON.stringify(reticle)}`,
      loadColumns: () => source.loadColumns(),
      loadRows: (query) => source.loadRows({ ...query, filters, reticle }),
      loadDistinctValues: (query) => source.loadDistinctValues({ ...query, filters, reticle }),
    };
  });

  const galleryQuery = computed<Omit<ScGalleryDataQuery, "mode" | "offset" | "limit">>(() => ({
    filters: tableBaseFilters.value,
    reticle: args.reticle.value,
    tableFilter: args.tableFilter.value,
    tableSort: args.tableSort.value,
    tableSelection: tableSelection.value,
  }));

  async function loadMap(): Promise<void> {
    const source = args.dataSource.value;
    const sequence = ++mapLoadSequence;
    if (!source) {
      mapArrowData.value = null;
      mapLoading.value = false;
      return;
    }
    mapLoading.value = true;
    mapError.value = null;
    mapProgressMessage.value = "Querying filtered map data";
    mapProgressPercent.value = 20;
    try {
      const ipc = await source.loadMap({
        filters: aggregateFilters.value,
        legendColumn: mapLegendColumn.value,
        reticle: args.reticle.value,
      });
      if (sequence !== mapLoadSequence || source !== args.dataSource.value) return;
      mapArrowData.value = [transferableBuffer(ipc)];
      mapProgressMessage.value = "Map data ready";
      mapProgressPercent.value = 100;
    } catch (error) {
      if (sequence !== mapLoadSequence || source !== args.dataSource.value) return;
      mapError.value = error instanceof Error ? error.message : String(error);
      args.onRecoverableError?.("SQL map query failed", error);
    } finally {
      if (sequence === mapLoadSequence) mapLoading.value = false;
    }
  }

  async function loadAggregates(): Promise<void> {
    const source = args.dataSource.value;
    const sequence = ++aggregateLoadSequence;
    if (!source) {
      legendGroups.value = null;
      return;
    }
    try {
      const groups = await source.loadAggregates({
        filters: aggregateFilters.value,
        field: mapLegendColumn.value,
        reticle: args.reticle.value,
      });
      if (sequence !== aggregateLoadSequence || source !== args.dataSource.value) return;
      legendGroups.value = Object.fromEntries(
        Object.entries(groups).map(([key, count]) => [
          key,
          create(DefectListSchema, { count, defectIds: [] }),
        ]),
      );
    } catch (error) {
      if (sequence !== aggregateLoadSequence || source !== args.dataSource.value) return;
      args.onRecoverableError?.("SQL aggregate query failed", error);
    }
  }

  watch(
    [args.dataSource, aggregateFilters, mapLegendColumn, args.reticle, invalidationRevision],
    () => void loadMap(),
    { deep: true, immediate: true },
  );

  watch(
    [args.dataSource, aggregateFilters, mapLegendColumn, args.reticle, invalidationRevision],
    () => void loadAggregates(),
    { deep: true, immediate: true },
  );

  watch(
    args.dataSource,
    (source) => {
      unsubscribe?.();
      unsubscribe =
        source?.subscribeInvalidations((event) => {
          invalidationRevision.value = Math.max(invalidationRevision.value, event.revision);
        }) ?? null;
    },
    { immediate: true },
  );

  onScopeDispose(() => {
    mapLoadSequence += 1;
    aggregateLoadSequence += 1;
    unsubscribe?.();
  });

  async function queryBoxSelection(
    mode: "wafer" | "die" | "reticle",
    region: { x: number; y: number; w: number; h: number },
  ): Promise<number[]> {
    const source = args.dataSource.value;
    if (!source) return [];
    return source.resolveSelection({
      filters: aggregateFilters.value,
      reticle: args.reticle.value,
      constraint: {
        kind: "rectangle",
        mode,
        x: region.x,
        y: region.y,
        width: region.w,
        height: region.h,
      },
    });
  }

  async function queryLassoSelection(
    mode: "wafer" | "die" | "reticle",
    selection: ScMapLassoSelection,
  ): Promise<number[]> {
    const source = args.dataSource.value;
    if (!source) return [];
    return source.resolveSelection({
      filters: aggregateFilters.value,
      reticle: args.reticle.value,
      constraint: { kind: "polygon", mode, selection },
    });
  }

  async function queryLegendSelection(key: string | number): Promise<number[]> {
    const source = args.dataSource.value;
    if (!source) return [];
    return source.resolveSelection({
      filters: aggregateFilters.value,
      reticle: args.reticle.value,
      constraint: {
        kind: "legend",
        field: mapLegendColumn.value,
        value: isScMissingFilterValue(mapLegendColumn.value, key) ? null : key,
      },
    });
  }

  async function querySamplingCandidateCount(options: ScSamplingCandidateOptions): Promise<number> {
    const source = args.dataSource.value;
    if (!source) throw new Error("SC data source is not ready");
    const groups = await source.loadAggregates({
      filters: samplingCandidateFilters(options),
      field: mapLegendColumn.value,
      reticle: args.reticle.value,
    });
    return Object.values(groups).reduce((sum, count) => sum + count, 0);
  }

  async function querySamplingDefectIds(
    count: number,
    seed: number,
    options: ScSamplingCandidateOptions,
  ): Promise<number[]> {
    const source = args.dataSource.value;
    if (!source) throw new Error("SC data source is not ready");
    return source.resolveSelection({
      filters: samplingCandidateFilters(options),
      reticle: args.reticle.value,
      constraint: { kind: "random", limit: count, seed },
    });
  }

  async function loadGlobalDistinctValues(
    field: string,
    search: string,
  ): Promise<Array<string | number>> {
    const source = args.dataSource.value;
    if (!source) return [];
    return source.loadDistinctValues({
      field,
      search,
      limit: 500,
      filter: {},
      sort: null,
      filters: [],
      reticle: args.reticle.value,
    });
  }

  async function loadGlobalNumericRange(
    field: string,
  ): Promise<{ min: number; max: number } | null> {
    const source = args.dataSource.value;
    if (!source) return null;
    const filterWithoutCurrentField = { ...args.globalFilter.value };
    delete filterWithoutCurrentField[field];
    return source.loadNumericRange({
      field,
      filters: buildScDataFilters(filterWithoutCurrentField),
      reticle: args.reticle.value,
    });
  }

  async function applyMapSelection(ids: number[]): Promise<void> {
    mapSelection.value = { ids: sortedUniqueIds(ids) };
  }

  async function appendMapSelection(ids: number[]): Promise<number[]> {
    const next = sortedUniqueIds([...mapSelection.value.ids, ...ids]);
    mapSelection.value = { ids: next };
    return next;
  }

  async function clearMapSelection(): Promise<void> {
    mapSelection.value = { ids: [] };
  }

  function setMapSelectionMode(mode: ScMapSelectionMode): void {
    const ids = sortedUniqueIds(mapSelection.value.ids);
    if (ids.length === 0) return;
    const current = mapSelectionFilter.value;
    if (
      current?.mode === mode &&
      current.ids.length === ids.length &&
      current.ids.every((id, index) => id === ids[index])
    ) {
      return;
    }
    mapSelectionFilterHistory.value = [
      ...mapSelectionFilterHistory.value,
      current ? { mode: current.mode, ids: [...current.ids] } : null,
    ];
    mapSelectionFilter.value = { mode, ids };
  }

  function invertMapSelectionMode(): void {
    const current = mapSelectionFilter.value;
    if (!current) {
      setMapSelectionMode("exclude");
      return;
    }
    mapSelectionFilterHistory.value = [
      ...mapSelectionFilterHistory.value,
      { mode: current.mode, ids: [...current.ids] },
    ];
    mapSelectionFilter.value = {
      mode: current.mode === "include" ? "exclude" : "include",
      ids: [...current.ids],
    };
  }

  function undoMapSelectionMode(): void {
    if (mapSelectionFilterHistory.value.length === 0) return;
    const previous = mapSelectionFilterHistory.value.at(-1) ?? null;
    mapSelectionFilterHistory.value = mapSelectionFilterHistory.value.slice(0, -1);
    mapSelectionFilter.value = previous ? { mode: previous.mode, ids: [...previous.ids] } : null;
  }

  function resetMapSelectionMode(): void {
    mapSelectionFilterHistory.value = [];
    mapSelectionFilter.value = null;
  }

  function setTableSelection(selection: ScTableSelectionConstraint): void {
    tableSelection.value =
      selection.kind === "all"
        ? { kind: "all", excludedIds: sortedUniqueIds(selection.excludedIds) }
        : { kind: "ids", ids: sortedUniqueIds(selection.ids) };
  }

  function setReviewMode(value: boolean): void {
    reviewMode.value = value;
  }

  return {
    mapArrowData,
    mapLegendColumn,
    legendGroups,
    galleryLoading: ref(false),
    galleryQuery,
    sampleTableDataSource,
    mapLoading,
    activeMapLoading: computed(() => mapLoading.value || mapArrowData.value === null),
    mapError,
    mapProgressMessage,
    mapProgressPercent,
    retryMap: loadMap,
    mapSelectedDefectIds,
    mapSelectionMode,
    canUndoMapSelectionMode,
    reviewMode,
    tableSelection,
    loadGlobalDistinctValues,
    loadGlobalNumericRange,
    setTableSelection,
    setReviewMode,
    queryBoxSelection,
    queryLassoSelection,
    queryLegendSelection,
    querySamplingCandidateCount,
    querySamplingDefectIds,
    applyMapSelection,
    appendMapSelection,
    clearMapSelection,
    setMapSelectionMode,
    invertMapSelectionMode,
    undoMapSelectionMode,
    resetMapSelectionMode,
  };
}
