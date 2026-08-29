import { buildScGlobalDataFilters } from "@/features/sc/application/workbenchDataFilter";
import {
  cloneScGlobalFilter,
  createScGlobalFilterGroup,
  createScGlobalFilterItem,
  type ScGlobalFilter,
} from "@/features/sc/domain/globalFilter";
import type {
  ScDataFilter,
  ScDataFilterExpression,
} from "@/features/sc/domain/workbenchDataSource";
import type { ScTableSelectionConstraint } from "@/features/sc/domain/workbenchDataSource";
import type { ScMapSelectionMode } from "@/features/sc/domain/workbenchInteraction";

export interface ScInspectionFilterPlan {
  globalFilters: ScDataFilterExpression[];
  mapFilters: ScDataFilterExpression[];
  aggregateFilters: ScDataFilterExpression[];
  tableFilters: ScDataFilterExpression[];
  galleryBaseFilters: ScDataFilterExpression[];
}

export type ScSamplingCandidateScope = "all" | "map" | "table";

export interface ScSamplingFilterOptions {
  scope: ScSamplingCandidateScope;
  extraFilterEnabled: boolean;
  extraFilter: ScGlobalFilter;
}

function uniqueNumericIds(ids: readonly (number | string)[]): number[] {
  return [...new Set(ids.map(Number).filter(Number.isFinite))];
}

function uniqueRowKeys(ids: readonly string[]): string[] {
  return [...new Set(ids.map(String).filter((id) => id.length > 0))];
}

export function applyMapSelectionToGlobalFilter(
  filter: ScGlobalFilter,
  selectedIds: readonly number[],
  mode: ScMapSelectionMode,
): ScGlobalFilter {
  const selected = uniqueNumericIds(selectedIds);
  if (selected.length === 0) throw new Error("Current map selection is empty");
  const next = cloneScGlobalFilter(filter);
  const committedItem = createScGlobalFilterItem({
    field: "map_id",
    condition: {
      filterType: "set",
      values: selected,
      ...(mode === "exclude" ? { exclude: true } : {}),
    },
    source: {
      kind: "map-selection",
      action: mode === "exclude" ? "exclude-selected" : "include-only",
    },
  });
  if (next.items.length === 0 || next.combinator === "and") {
    next.combinator = "and";
    next.items.push(committedItem);
    return next;
  }
  return {
    combinator: "and",
    items: [
      createScGlobalFilterGroup({ combinator: next.combinator, items: next.items }),
      committedItem,
    ],
  };
}

export function buildInspectionFilterPlan(args: {
  globalFilter: ScGlobalFilter;
  mapSelectionIds: readonly number[];
  reviewMode: boolean;
  samplingIds: ReadonlySet<string> | undefined;
}): ScInspectionFilterPlan {
  const globalFilters = buildScGlobalDataFilters(args.globalFilter);
  const mapSelectionIds = uniqueNumericIds(args.mapSelectionIds);
  const samplingIds = uniqueNumericIds([...(args.samplingIds ?? [])]);
  const transientFilters: ScDataFilterExpression[] = [
    ...(mapSelectionIds.length > 0 ? ([["map_id", "in", mapSelectionIds]] as ScDataFilter[]) : []),
    ...(samplingIds.length > 0 ? ([["map_id", "in", samplingIds]] as ScDataFilter[]) : []),
  ];
  const tableExtraFilters: ScDataFilterExpression[] = [
    ...transientFilters,
    ...(args.reviewMode ? ([["images", ">", 0]] as ScDataFilter[]) : []),
  ];
  const tableFilters = [...globalFilters, ...tableExtraFilters];
  const galleryBaseFilters = [...tableFilters];

  return {
    globalFilters,
    mapFilters: globalFilters,
    aggregateFilters: globalFilters,
    tableFilters,
    galleryBaseFilters,
  };
}

export function buildSamplingCandidateFilters(args: {
  baseFilter: ScGlobalFilter;
  mapSelectionIds: readonly number[];
  tableSelection: ScTableSelectionConstraint;
  options: ScSamplingFilterOptions;
}): ScDataFilterExpression[] {
  const mapSelectionIds = uniqueNumericIds(args.mapSelectionIds);
  if (args.options.scope === "map" && mapSelectionIds.length === 0) {
    throw new Error("Current map selection is empty");
  }
  const tableSelectionIds =
    args.tableSelection.kind === "ids"
      ? uniqueRowKeys([...args.tableSelection.ids])
      : uniqueRowKeys([...args.tableSelection.excludedIds]);
  if (
    args.options.scope === "table" &&
    args.tableSelection.kind === "ids" &&
    tableSelectionIds.length === 0
  ) {
    throw new Error("Current table selection is empty");
  }
  return [
    ...buildScGlobalDataFilters(args.baseFilter),
    ...(args.options.extraFilterEnabled ? buildScGlobalDataFilters(args.options.extraFilter) : []),
    ...(args.options.scope === "map"
      ? ([["map_id", "in", mapSelectionIds]] as ScDataFilter[])
      : []),
    ...(args.options.scope === "table" && args.tableSelection.kind === "ids"
      ? ([["row_key", "in", tableSelectionIds]] as ScDataFilter[])
      : []),
    ...(args.options.scope === "table" &&
    args.tableSelection.kind === "all" &&
    tableSelectionIds.length > 0
      ? ([["row_key", "not in", tableSelectionIds]] as ScDataFilter[])
      : []),
  ];
}
