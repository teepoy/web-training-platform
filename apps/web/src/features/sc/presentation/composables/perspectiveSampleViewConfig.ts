import type { Filter, ViewConfigUpdate } from "@perspective-dev/client";
import type { ScSampleTableFilter, ScSampleTableSort } from "@/features/sc/domain/sampleTable";
import { buildPerspectiveFilters, perspectiveFilterField } from "./perspectiveFilter";

const DEFAULT_SAMPLE_SORT: NonNullable<ViewConfigUpdate["sort"]> = [["defect_id", "asc"]];

interface PerspectiveSampleViewConfigOptions {
  base?: ViewConfigUpdate;
  tableFilter?: ScSampleTableFilter;
  tableSort?: ScSampleTableSort | null;
  additionalFilters?: readonly Filter[];
  omitTableFilterField?: string;
}

/**
 * Builds the effective Perspective view shared by the sample table and gallery.
 *
 * `base` contains context owned by the quad/model (global, map, sampling, and
 * review filters). Header filters and sorting are then applied consistently.
 */
export function buildPerspectiveSampleViewConfig({
  base = {},
  tableFilter,
  tableSort,
  additionalFilters = [],
  omitTableFilterField,
}: PerspectiveSampleViewConfigOptions): ViewConfigUpdate {
  const filter = [
    ...(base.filter ?? []),
    ...additionalFilters,
    ...buildPerspectiveFilters(tableFilter, { omitField: omitTableFilterField }),
  ];
  const sort: NonNullable<ViewConfigUpdate["sort"]> = tableSort?.direction
    ? [[perspectiveFilterField(tableSort.field), tableSort.direction]]
    : DEFAULT_SAMPLE_SORT;
  const config: ViewConfigUpdate = {
    ...base,
    sort,
  };
  if (filter.length > 0) config.filter = filter;
  else delete config.filter;
  return config;
}
