import type { ScDataFilter } from "@/features/sc/domain/workbenchDataSource";
import type { ScSampleTableFilter } from "@/features/sc/domain/sampleTable";

export function buildScDataFilters(
  filter: ScSampleTableFilter | undefined,
  options: { omitField?: string } = {},
): ScDataFilter[] {
  const result: ScDataFilter[] = [];
  for (const [field, condition] of Object.entries(filter ?? {})) {
    if (field === options.omitField) continue;
    if (condition.filterType === "set" && condition.values.length > 0) {
      result.push([field, "in", condition.values]);
    } else if (condition.filterType === "number" && condition.type === "inRange") {
      result.push([field, ">=", condition.filter], [field, "<=", condition.filterTo]);
    }
  }
  return result;
}
