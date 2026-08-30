import type { ScSampleTableFilter } from "./sampleTable";
import type { SampleFilterRequest } from "@/generated/orval/models/sampleFilterRequest";

export type ScFilterCondition = ScSampleTableFilter[string];
export type ScFilterCombinator = "and" | "or";

export type ScGlobalFilterItemSource =
  | { kind: "manual" }
  | {
      kind: "map-selection";
      action: "exclude-selected" | "include-only";
    };

export interface ScGlobalFilterItem {
  id: string;
  field: string;
  condition: ScFilterCondition;
  source: ScGlobalFilterItemSource;
}

export interface ScGlobalFilterGroup {
  kind: "group";
  id: string;
  combinator: ScFilterCombinator;
  items: ScGlobalFilterNode[];
}

export type ScGlobalFilterNode = ScGlobalFilterItem | ScGlobalFilterGroup;

export interface ScGlobalFilter {
  combinator: ScFilterCombinator;
  items: ScGlobalFilterNode[];
}

export type ScWorkflowSampleFilter = SampleFilterRequest;

export function emptyScGlobalFilter(): ScGlobalFilter {
  return { combinator: "and", items: [] };
}

export function createScGlobalFilterItemId(): string {
  const randomUuid = globalThis.crypto?.randomUUID;
  if (!randomUuid) throw new Error("The browser cannot create a stable Global Filter item ID");
  return randomUuid.call(globalThis.crypto);
}

export function isScGlobalFilterGroup(node: ScGlobalFilterNode): node is ScGlobalFilterGroup {
  return "kind" in node && node.kind === "group";
}

export function cloneScFilterCondition(condition: ScFilterCondition): ScFilterCondition {
  return condition.filterType === "set"
    ? { ...condition, values: [...condition.values] }
    : { ...condition };
}

export function cloneScGlobalFilter(filter: ScGlobalFilter): ScGlobalFilter {
  return {
    combinator: filter.combinator,
    items: filter.items.map(cloneScGlobalFilterNode),
  };
}

export function cloneScGlobalFilterNode(node: ScGlobalFilterNode): ScGlobalFilterNode {
  return isScGlobalFilterGroup(node)
    ? {
        kind: "group",
        id: node.id,
        combinator: node.combinator,
        items: node.items.map(cloneScGlobalFilterNode),
      }
    : {
        ...node,
        condition: cloneScFilterCondition(node.condition),
        source: { ...node.source },
      };
}

export function createScGlobalFilterItem(args: {
  field: string;
  condition: ScFilterCondition;
  source?: ScGlobalFilterItemSource;
  id?: string;
}): ScGlobalFilterItem {
  const field = args.field.trim();
  if (!field) throw new Error("Global Filter item field is required");
  return {
    id: args.id ?? createScGlobalFilterItemId(),
    field,
    condition: cloneScFilterCondition(args.condition),
    source: args.source ?? { kind: "manual" },
  };
}

export function createScGlobalFilterGroup(
  args: {
    combinator?: ScFilterCombinator;
    items?: ScGlobalFilterNode[];
    id?: string;
  } = {},
): ScGlobalFilterGroup {
  return {
    kind: "group",
    id: args.id ?? createScGlobalFilterItemId(),
    combinator: args.combinator ?? "and",
    items: (args.items ?? []).map(cloneScGlobalFilterNode),
  };
}

export function scGlobalFilterConditionCount(filter: ScGlobalFilter): number {
  return filter.items.reduce((count, node) => count + scGlobalFilterNodeConditionCount(node), 0);
}

function scGlobalFilterNodeConditionCount(node: ScGlobalFilterNode): number {
  return isScGlobalFilterGroup(node)
    ? node.items.reduce((count, child) => count + scGlobalFilterNodeConditionCount(child), 0)
    : 1;
}

export function scGlobalFilterConditions(filter: ScGlobalFilter): ScGlobalFilterItem[] {
  return filter.items.flatMap(scGlobalFilterNodeConditions);
}

function scGlobalFilterNodeConditions(node: ScGlobalFilterNode): ScGlobalFilterItem[] {
  return isScGlobalFilterGroup(node) ? node.items.flatMap(scGlobalFilterNodeConditions) : [node];
}

export function scGlobalFilterHasConditions(filter: ScGlobalFilter): boolean {
  return scGlobalFilterConditionCount(filter) > 0;
}

export function combineScGlobalFilters(
  ...filters: Array<ScGlobalFilter | null | undefined>
): ScGlobalFilter {
  const effective = filters.filter(
    (filter): filter is ScGlobalFilter => !!filter && scGlobalFilterHasConditions(filter),
  );
  if (effective.length === 0) return emptyScGlobalFilter();
  if (effective.length === 1) return cloneScGlobalFilter(effective[0]!);
  return {
    combinator: "and",
    items: effective.flatMap((filter) => {
      const clonedFilter = cloneScGlobalFilter(filter);
      return clonedFilter.combinator === "and"
        ? clonedFilter.items
        : [createScGlobalFilterGroup({ combinator: "or", items: clonedFilter.items })];
    }),
  };
}

export function toScWorkflowSampleFilter(filter: ScGlobalFilter): ScWorkflowSampleFilter | null {
  const items = filter.items
    .map(toScWorkflowSampleFilterNode)
    .filter((node): node is NonNullable<typeof node> => node !== null);
  if (items.length === 0) return null;
  return {
    combinator: filter.combinator,
    items,
  };
}

function toScWorkflowSampleFilterNode(
  node: ScGlobalFilterNode,
): ScWorkflowSampleFilter["items"][number] | null {
  if (isScGlobalFilterGroup(node)) {
    const items = node.items
      .map(toScWorkflowSampleFilterNode)
      .filter((child): child is NonNullable<typeof child> => child !== null);
    if (items.length === 0) return null;
    return {
      kind: "group",
      combinator: node.combinator,
      items,
    };
  }
  if (node.condition.filterType === "set" && node.condition.values.length === 0) {
    return null;
  }
  return {
    kind: "condition",
    field: node.field,
    condition:
      node.condition.filterType === "set"
        ? {
            filterType: "set",
            values: [...node.condition.values],
            ...(node.condition.exclude ? { exclude: true } : {}),
          }
        : {
            filterType: "number",
            type: "inRange",
            filter: node.condition.filter,
            filterTo: node.condition.filterTo,
          },
  };
}
