import type {
  ScDataFilter,
  ScDataFilterExpression,
} from "@/features/sc/domain/workbenchDataSource";
import type { ScSampleTableFilter } from "@/features/sc/domain/sampleTable";
import {
  isScGlobalFilterGroup,
  type ScFilterCondition,
  type ScGlobalFilter,
  type ScGlobalFilterNode,
} from "@/features/sc/domain/globalFilter";
import { splitScSetFilterValues } from "@/features/sc/domain/missingFilterValue";

function buildScConditionFilters(field: string, condition: ScFilterCondition): ScDataFilter[] {
  if (condition.filterType === "set") {
    if (condition.values.length === 0) return [];
    const setFilter = splitScSetFilterValues(field, condition.values);
    const operator = condition.exclude
      ? setFilter.includeMissing
        ? "not in and not null"
        : "not in or null"
      : setFilter.includeMissing
        ? "in or null"
        : "in";
    return [[field, operator, setFilter.values]];
  }
  if (condition.filterType === "number" && condition.type === "inRange") {
    return [
      [field, ">=", condition.filter],
      [field, "<=", condition.filterTo],
    ];
  }
  return [];
}

export function buildScDataFilters(
  filter: ScSampleTableFilter | undefined,
  options: { omitField?: string } = {},
): ScDataFilter[] {
  const result: ScDataFilter[] = [];
  for (const [field, condition] of Object.entries(filter ?? {})) {
    if (field === options.omitField) continue;
    result.push(...buildScConditionFilters(field, condition));
  }
  return result;
}

export function buildScGlobalDataFilters(
  filter: ScGlobalFilter,
  options: { omitItemId?: string } = {},
): ScDataFilterExpression[] {
  const items = filter.items
    .map((node) => buildScGlobalNodeExpression(node, options.omitItemId))
    .filter((node): node is ScDataFilterExpression => node !== null);
  return items.length > 0 ? [{ combinator: filter.combinator, items }] : [];
}

function buildScGlobalNodeExpression(
  node: ScGlobalFilterNode,
  omitItemId: string | undefined,
): ScDataFilterExpression | null {
  if (isScGlobalFilterGroup(node)) {
    const items = node.items
      .map((child) => buildScGlobalNodeExpression(child, omitItemId))
      .filter((child): child is ScDataFilterExpression => child !== null);
    return items.length > 0 ? { combinator: node.combinator, items } : null;
  }
  if (node.id === omitItemId) return null;
  const conditions = buildScConditionFilters(node.field, node.condition);
  if (conditions.length === 0) return null;
  return conditions.length === 1 ? conditions[0]! : { combinator: "and", items: conditions };
}
