import type { BrowserItem } from "../types/components";

export interface BrowserFilterParams {
  activeLabelFilter?: string | null;
  collectionFilterIds?: string[];
}

/**
 * Pure filter: given an array of BrowserItem and filter criteria,
 * returns the filtered subset. Does not depend on interaction-state
 * types or any apps/web imports.
 */
export function filterBrowserItems(
  items: BrowserItem[],
  filter: BrowserFilterParams,
): BrowserItem[] {
  let result = items;

  if (filter.activeLabelFilter) {
    const label = filter.activeLabelFilter;
    result = result.filter(
      (item) => item.currentLabel === label || item.draftLabel === label,
    );
  }

  if (filter.collectionFilterIds && filter.collectionFilterIds.length > 0) {
    const idSet = new Set(filter.collectionFilterIds);
    result = result.filter((item) => idSet.has(item.id));
  }

  return result;
}
