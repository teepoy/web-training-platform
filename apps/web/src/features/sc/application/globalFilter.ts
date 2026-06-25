import type { ScMapFilter } from "@/features/sc/api/plotPoints";
import type { ScSampleTableFilter } from "@/features/sc/domain/sampleTable";

export function sampleTableFilterToMapFilter(filter?: ScSampleTableFilter): ScMapFilter {
  const mapFilter: ScMapFilter = {};
  if (!filter) return mapFilter;

  for (const [field, value] of Object.entries(filter)) {
    if (value?.operator !== "in") continue;
    const numbers = value.values
      .map((item) => Number(item))
      .filter((item) => Number.isFinite(item));
    if (numbers.length === 0) continue;
    if (field === "class_number") mapFilter.class_numbers = numbers;
    else if (field === "rough_bin") mapFilter.rough_bins = numbers;
    else if (field === "test_id") mapFilter.test_ids = numbers;
    else if (field === "adder") mapFilter.adders = numbers;
    else if (field === "cluster_id") mapFilter.cluster_ids = numbers;
  }

  return mapFilter;
}

export function hasSampleTableFilter(filter?: ScSampleTableFilter): boolean {
  return Boolean(filter && Object.keys(filter).length > 0);
}
