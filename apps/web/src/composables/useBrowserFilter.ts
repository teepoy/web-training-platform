import { computed, type ComputedRef, type Ref } from "vue";
import type { BrowserItem } from "../types";
import type { SidebarWidgetInteractionState } from "../components/classify/widgetContract";

export function useBrowserFilter(
  items: Ref<BrowserItem[]>,
  interactionState: Ref<SidebarWidgetInteractionState>,
): { filteredItems: ComputedRef<BrowserItem[]> } {
  const filteredItems = computed<BrowserItem[]>(() => {
    const state = interactionState.value;
    let result = items.value;

    if (state.activeLabelFilter) {
      const label = state.activeLabelFilter;
      result = result.filter(
        (item) => item.currentLabel === label || item.draftLabel === label,
      );
    }

    const browserCollection = state.collections?.["browser-items"];
    if (
      browserCollection &&
      browserCollection.filter.mode === "selected-only" &&
      browserCollection.filter.ids.length > 0
    ) {
      const idSet = new Set(browserCollection.filter.ids);
      result = result.filter((item) => idSet.has(item.id));
    }

    return result;
  });

  return { filteredItems };
}
