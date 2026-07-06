import type { Filter } from "@perspective-dev/client";
import type { ScSampleTableFilter } from "@/features/sc/domain/sampleTable";

export function perspectiveFilterField(field: string): string {
  if (field === "annotation_label") return "annotation_label";
  if (field === "prediction_label") return "prediction_label";
  if (field === "final_class") return "final_class";
  if (field === "class_number") return "class_number";
  return field;
}

export function buildPerspectiveFilters(
  filter: ScSampleTableFilter | undefined,
  options: { omitField?: string } = {},
): Filter[] {
  const result: Filter[] = [];
  for (const [field, condition] of Object.entries(filter ?? {})) {
    if (field === options.omitField) continue;
    const column = perspectiveFilterField(field);
    if (condition.filterType === "set" && condition.values.length > 0) {
      result.push([column, "in", condition.values] as Filter);
    } else if (condition.filterType === "number" && condition.type === "inRange") {
      result.push(
        [column, ">=", condition.filter] as Filter,
        [column, "<=", condition.filterTo] as Filter,
      );
    }
  }
  return result;
}
