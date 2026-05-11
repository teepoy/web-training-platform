import { computed, type ComputedRef, type Ref } from "vue";
import { filterBrowserItems } from "@platform/web-ui";
import type { BrowserItem } from "../types";
import type { SidebarWidgetInteractionState } from "../components/classify/widgetContract";

export function useBrowserFilter(
  items: Ref<BrowserItem[]>,
  interactionState: Ref<SidebarWidgetInteractionState>,
  collectionKey: string = "browser-items"
): { filteredItems: ComputedRef<BrowserItem[]> } {
  const filteredItems = computed<BrowserItem[]>(() => {
    const state = interactionState.value;

    const browserCollection = state.collections?.[collectionKey];
    const collectionFilterIds =
      browserCollection?.filter.mode === "selected-only" &&
      browserCollection.filter.ids.length > 0
        ? browserCollection.filter.ids
        : undefined;

    return filterBrowserItems(items.value, {
      activeLabelFilter: state.activeLabelFilter,
      collectionFilterIds,
    });
  });

  return { filteredItems };
}
