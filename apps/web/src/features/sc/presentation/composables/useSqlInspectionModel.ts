import { create } from "@bufbuild/protobuf";
import { computed, onScopeDispose, ref, watch, type ComputedRef, type Ref } from "vue";
import type { DefectList } from "@/features/sc/generated/proto/sc/v1/sample_pb";
import { DefectListSchema } from "@/features/sc/generated/proto/sc/v1/sample_pb";
import { buildScGlobalDataFilters } from "@/features/sc/application/workbenchDataFilter";
import {
  buildInspectionFilterPlan,
  buildSamplingCandidateFilters,
  type ScSamplingFilterOptions,
} from "@/features/sc/application/inspectionFilterPolicy";
import { isScMissingFilterValue } from "@/features/sc/domain/missingFilterValue";
import type { ReticleMapOptions } from "@/features/sc/application/reticleMapOptions";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import type { ScGlobalFilter } from "@/features/sc/domain/globalFilter";
import type {
  ScSamplingGroupPopulation,
  ScSamplingProgram,
} from "@/features/sc/domain/samplingRules";
import type {
  ScDataFilterExpression,
  ScGalleryDataQuery,
  ScReticleProjection,
  ScTableSelectionConstraint,
  ScWorkbenchDataSource,
} from "@/features/sc/domain/workbenchDataSource";
import type {
  ScLegendSource,
  ScSampleTableDataSource,
} from "@/features/sc/domain/workbenchInteraction";
import type { ScMapLassoSelection } from "@platform/sc-map-element";

interface IdSelectionState {
  ids: number[];
}

export type ScSamplingCandidateOptions = ScSamplingFilterOptions;

function sortedUniqueIds(ids: readonly number[]): number[] {
  return [...new Set(ids.filter(Number.isFinite))].sort((left, right) => left - right);
}

function sortedUniqueKeys(ids: readonly string[]): string[] {
  return [...new Set(ids.filter((id) => id.length > 0))].sort();
}

function legendColumn(source: ScLegendSource | null | undefined): string {
  if (source === "bin") return "rough_bin";
  if (source === "annotation") return "annotation_label";
  if (source === "prediction") return "prediction_label";
  if (source === "final_class") return "final_class";
  return "class_number";
}

function hiddenLegendValue(field: string, key: string): string | number | null {
  if (isScMissingFilterValue(field, key) || key === "__unlabeled__") return null;
  if (field !== "class_number" && field !== "rough_bin") return key;
  const value = Number(key);
  if (!Number.isFinite(value)) {
    throw new Error(`Invalid hidden legend key "${key}" for numeric field "${field}"`);
  }
  return value;
}

function transferableBuffer(value: Uint8Array): ArrayBuffer {
  return value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength) as ArrayBuffer;
}

export function useSqlInspectionModel(args: {
  dataSource: Ref<ScWorkbenchDataSource | null> | ComputedRef<ScWorkbenchDataSource | null>;
  legendGroupBy: ComputedRef<ScLegendSource | null | undefined>;
  globalFilter: ComputedRef<ScGlobalFilter>;
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
  const tableSelection = ref<ScTableSelectionConstraint>({ kind: "ids", ids: [] });
  const mapSelectedDefectIds = computed(() => mapSelection.value.ids);
  const reviewMode = ref(false);
  const invalidationRevision = ref(0);
  let mapLoadSequence = 0;
  let aggregateLoadSequence = 0;
  let unsubscribe: (() => void) | null = null;

  const requestedMapLegendColumn = computed(() => legendColumn(args.legendGroupBy.value));
  const mapLegendColumn = ref(requestedMapLegendColumn.value);
  const globalFilters = computed(() => buildScGlobalDataFilters(args.globalFilter.value));
  const filterPlan = computed(() =>
    buildInspectionFilterPlan({
      globalFilter: args.globalFilter.value,
      mapSelectionIds: mapSelection.value.ids,
      reviewMode: reviewMode.value,
      samplingIds: args.galleryRandomSamplingDefectIds.value,
    }),
  );
  function mapSelectionFilters(hiddenLegendKeys: readonly string[]): ScDataFilterExpression[] {
    if (hiddenLegendKeys.length === 0) return filterPlan.value.selectionFilters;
    const field = requestedMapLegendColumn.value;
    const hiddenValues = [...new Set(hiddenLegendKeys.map((key) => hiddenLegendValue(field, key)))];
    const excludesMissing = hiddenValues.includes(null);
    const concreteValues = hiddenValues.filter((value): value is string | number => value !== null);
    return [
      ...filterPlan.value.selectionFilters,
      [field, excludesMissing ? "not in and not null" : "not in or null", concreteValues],
    ];
  }
  function samplingCandidateFilters(options: ScSamplingCandidateOptions): ScDataFilterExpression[] {
    return buildSamplingCandidateFilters({
      baseFilter: args.globalFilter.value,
      mapSelectionIds: mapSelection.value.ids,
      tableSelection: tableSelection.value,
      options,
    });
  }

  const sampleTableDataSource = computed<ScSampleTableDataSource | undefined>(() => {
    const source = args.dataSource.value;
    if (!source) return undefined;
    const filters = filterPlan.value.tableFilters;
    const reticle = args.reticle.value;
    return {
      scopeKey: `${source.scopeKey}:${JSON.stringify(filters)}:${JSON.stringify(reticle)}`,
      loadColumns: () => source.loadColumns(),
      loadRows: (query) => source.loadRows({ ...query, filters, reticle }),
      loadDistinctValues: (query) => source.loadDistinctValues({ ...query, filters, reticle }),
    };
  });

  const galleryQuery = computed<Omit<ScGalleryDataQuery, "mode" | "offset" | "limit">>(() => ({
    filters: filterPlan.value.galleryBaseFilters,
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
    const targetLegendColumn = requestedMapLegendColumn.value;
    try {
      const ipc = await source.loadMap({
        filters: filterPlan.value.mapFilters,
        legendColumn: targetLegendColumn,
        reticle: args.reticle.value,
      });
      if (sequence !== mapLoadSequence || source !== args.dataSource.value) return;
      mapLegendColumn.value = targetLegendColumn;
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
        filters: filterPlan.value.aggregateFilters,
        field: requestedMapLegendColumn.value,
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
    [args.dataSource, globalFilters, requestedMapLegendColumn, args.reticle, invalidationRevision],
    () => void loadMap(),
    { deep: true, immediate: true },
  );

  watch(
    [args.dataSource, globalFilters, requestedMapLegendColumn, args.reticle, invalidationRevision],
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
    hiddenLegendKeys: readonly string[] = [],
  ): Promise<number[]> {
    const source = args.dataSource.value;
    if (!source) return [];
    return source.resolveSelection({
      filters: mapSelectionFilters(hiddenLegendKeys),
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
    hiddenLegendKeys: readonly string[] = [],
  ): Promise<number[]> {
    const source = args.dataSource.value;
    if (!source) return [];
    return source.resolveSelection({
      filters: mapSelectionFilters(hiddenLegendKeys),
      reticle: args.reticle.value,
      constraint: { kind: "polygon", mode, selection },
    });
  }

  async function queryLegendSelection(
    key: string | number,
    hiddenLegendKeys: readonly string[] = [],
  ): Promise<number[]> {
    const source = args.dataSource.value;
    if (!source) return [];
    return source.resolveSelection({
      filters: mapSelectionFilters(hiddenLegendKeys),
      reticle: args.reticle.value,
      constraint: {
        kind: "legend",
        field: requestedMapLegendColumn.value,
        value: isScMissingFilterValue(requestedMapLegendColumn.value, key) ? null : key,
      },
    });
  }

  async function querySamplingCandidateCount(options: ScSamplingCandidateOptions): Promise<number> {
    const source = args.dataSource.value;
    if (!source) throw new Error("SC data source is not ready");
    const groups = await source.loadAggregates({
      filters: samplingCandidateFilters(options),
      field: requestedMapLegendColumn.value,
      reticle: args.reticle.value,
    });
    return Object.values(groups).reduce((sum, count) => sum + count, 0);
  }

  async function querySamplingDefectIds(
    program: ScSamplingProgram,
    seed: number,
    options: ScSamplingCandidateOptions,
  ): Promise<number[]> {
    const source = args.dataSource.value;
    if (!source) throw new Error("SC data source is not ready");
    return source.resolveSelection({
      filters: samplingCandidateFilters(options),
      reticle: args.reticle.value,
      constraint: { kind: "sampling-program", program, seed },
    });
  }

  async function querySamplingGroups(
    field: string,
    options: ScSamplingCandidateOptions,
  ): Promise<ScSamplingGroupPopulation[]> {
    const source = args.dataSource.value;
    if (!source) throw new Error("SC data source is not ready");
    const groups = await source.loadAggregates({
      filters: samplingCandidateFilters(options),
      field,
      reticle: args.reticle.value,
    });
    return Object.entries(groups)
      .map(([value, count]) => ({ value, count }))
      .sort((left, right) => left.value.localeCompare(right.value, undefined, { numeric: true }));
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
    omitItemId?: string,
  ): Promise<{ min: number; max: number } | null> {
    return loadFilterNumericRange(args.globalFilter.value, field, omitItemId);
  }

  async function loadFilterNumericRange(
    filter: ScGlobalFilter,
    field: string,
    omitItemId?: string,
  ): Promise<{ min: number; max: number } | null> {
    const source = args.dataSource.value;
    if (!source) return null;
    return source.loadNumericRange({
      field,
      filters: buildScGlobalDataFilters(filter, { omitItemId }),
      reticle: args.reticle.value,
    });
  }

  async function queryAllMapSelection(hiddenLegendKeys: readonly string[] = []): Promise<number[]> {
    const source = args.dataSource.value;
    if (!source) return [];
    return source.resolveSelection({
      filters: mapSelectionFilters(hiddenLegendKeys),
      reticle: args.reticle.value,
      constraint: { kind: "all" },
    });
  }

  async function queryVisibleMapSelection(
    ids: readonly number[],
    hiddenLegendKeys: readonly string[] = [],
  ): Promise<number[]> {
    const source = args.dataSource.value;
    if (!source || ids.length === 0) return [];
    return source.resolveSelection({
      filters: mapSelectionFilters(hiddenLegendKeys),
      reticle: args.reticle.value,
      constraint: { kind: "ids", ids: sortedUniqueIds(ids) },
    });
  }

  function updateMapSelection(ids: readonly number[]): number[] {
    const next = sortedUniqueIds(ids);
    mapSelection.value = { ids: next };
    return next;
  }

  function applyMapSelection(ids: number[]): void {
    updateMapSelection(ids);
  }

  function appendMapSelection(ids: number[]): number[] {
    return updateMapSelection([...mapSelection.value.ids, ...ids]);
  }

  function clearMapSelection(): void {
    updateMapSelection([]);
  }

  function setTableSelection(selection: ScTableSelectionConstraint): void {
    tableSelection.value =
      selection.kind === "all"
        ? { kind: "all", excludedIds: sortedUniqueKeys(selection.excludedIds) }
        : { kind: "ids", ids: sortedUniqueKeys(selection.ids) };
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
    reviewMode,
    tableSelection,
    loadGlobalDistinctValues,
    loadGlobalNumericRange,
    loadFilterNumericRange,
    setTableSelection,
    setReviewMode,
    queryBoxSelection,
    queryLassoSelection,
    queryLegendSelection,
    queryAllMapSelection,
    queryVisibleMapSelection,
    querySamplingCandidateCount,
    querySamplingDefectIds,
    querySamplingGroups,
    applyMapSelection,
    appendMapSelection,
    clearMapSelection,
  };
}
