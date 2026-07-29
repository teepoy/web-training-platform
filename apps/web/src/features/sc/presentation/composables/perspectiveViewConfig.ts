import type { ViewConfigUpdate } from "@perspective-dev/client";

export type PerspectiveViewConfig = ViewConfigUpdate;

export function perspectiveViewConfigKey(config: PerspectiveViewConfig): string {
  return JSON.stringify({
    columns: config.columns,
    expressions: config.expressions,
    filter: config.filter,
    sort: config.sort,
    groupBy: config.group_by,
    aggregates: config.aggregates,
  });
}
