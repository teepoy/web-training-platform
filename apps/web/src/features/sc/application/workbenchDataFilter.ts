import type { ScDataFilter } from "@/features/sc/domain/workbenchDataSource";
import type { ScSampleTableFilter } from "@/features/sc/domain/sampleTable";
import { splitScSetFilterValues } from "@/features/sc/domain/missingFilterValue";

export function buildScDataFilters(
  filter: ScSampleTableFilter | undefined,
  options: { omitField?: string } = {},
): ScDataFilter[] {
  const result: ScDataFilter[] = [];
  for (const [field, condition] of Object.entries(filter ?? {})) {
    if (field === options.omitField) continue;
    if (condition.filterType === "set" && condition.values.length > 0) {
      const setFilter = splitScSetFilterValues(field, condition.values);
      result.push([field, setFilter.includeMissing ? "in or null" : "in", setFilter.values]);
    } else if (condition.filterType === "number" && condition.type === "inRange") {
      result.push([field, ">=", condition.filter], [field, "<=", condition.filterTo]);
    }
  }
  return result;
}
