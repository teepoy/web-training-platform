import { computed, onScopeDispose, ref, watch, type ComputedRef, type Ref } from "vue";
import type {
  ScGalleryDataQuery,
  ScWorkbenchDataSource,
} from "@/features/sc/domain/workbenchDataSource";
import { SC_SCROLL_QUERY_DEBOUNCE_MS } from "./scrollQueryDebounce";

interface GalleryWindow<T> {
  items: T[];
  offset: number;
  total: number;
}

const SELECT_ALL_PAGE_ROWS = 2_000;

export async function loadAllGalleryItems<T>(
  source: ScWorkbenchDataSource,
  query: Omit<ScGalleryDataQuery, "offset" | "limit">,
  decode: (ipc: Uint8Array, offset: number) => T[],
  pageRows = SELECT_ALL_PAGE_ROWS,
): Promise<T[]> {
  if (!Number.isSafeInteger(pageRows) || pageRows <= 0) {
    throw new Error("Gallery selection page size must be a positive integer");
  }
  const items: T[] = [];
  let offset = 0;
  let total: number | null = null;
  while (total === null || offset < total) {
    const page = await source.loadGallery({ ...query, offset, limit: pageRows });
    total = page.total;
    if (!page.ipc) {
      if (total === 0) return [];
      throw new Error("Gallery selection returned no rows before reaching the reported total");
    }
    items.push(...decode(page.ipc, offset));
    if (page.nextOffset === null) {
      if (items.length < total) {
        throw new Error("Gallery selection ended before reaching the reported total");
      }
      break;
    }
    if (page.nextOffset <= offset) {
      throw new Error("Gallery selection cursor did not advance");
    }
    offset = page.nextOffset;
  }
  return items;
}

export function usePagedDataGallery<T>(
  dataSource: ComputedRef<ScWorkbenchDataSource | null>,
  query: ComputedRef<Omit<ScGalleryDataQuery, "offset" | "limit">>,
  requestedRange: Ref<{ start: number; end: number }>,
  enabled: ComputedRef<boolean>,
  decode: (ipc: Uint8Array, offset: number) => T[],
) {
  const window = ref<GalleryWindow<T>>({ items: [], offset: 0, total: 0 });
  const isPending = ref(false);
  const error = ref<string | null>(null);
  const revision = ref(0);
  let requestSequence = 0;
  let unsubscribe: (() => void) | null = null;
  let loadTimer: ReturnType<typeof setTimeout> | null = null;
  let loadedQueryKey = "";

  async function load(): Promise<void> {
    const source = dataSource.value;
    const sequence = ++requestSequence;
    if (!enabled.value) {
      isPending.value = false;
      return;
    }
    if (!source) {
      window.value = { items: [], offset: 0, total: 0 };
      loadedQueryKey = "";
      isPending.value = false;
      return;
    }
    const start = Math.max(0, requestedRange.value.start);
    const end = Math.max(start + 1, requestedRange.value.end);
    const queryKey = `${source.scopeKey}:${revision.value}:${JSON.stringify(query.value)}`;
    const loadedEnd = window.value.offset + window.value.items.length;
    if (
      queryKey === loadedQueryKey &&
      start >= window.value.offset &&
      (end <= loadedEnd || loadedEnd >= window.value.total)
    ) {
      isPending.value = false;
      return;
    }
    isPending.value = true;
    error.value = null;
    try {
      const page = await source.loadGallery({
        ...query.value,
        offset: start,
        limit: end - start,
      });
      if (sequence !== requestSequence || source !== dataSource.value) return;
      window.value = {
        items: page.ipc ? decode(page.ipc, start) : [],
        offset: start,
        total: page.total,
      };
      loadedQueryKey = queryKey;
    } catch (cause) {
      if (sequence !== requestSequence) return;
      error.value = cause instanceof Error ? cause.message : String(cause);
    } finally {
      if (sequence === requestSequence) isPending.value = false;
    }
  }

  function scheduleLoad(): void {
    requestSequence += 1;
    if (loadTimer !== null) clearTimeout(loadTimer);
    if (!enabled.value) {
      loadTimer = null;
      isPending.value = false;
      return;
    }
    loadTimer = setTimeout(() => {
      loadTimer = null;
      void load();
    }, SC_SCROLL_QUERY_DEBOUNCE_MS);
  }

  watch([dataSource, query, requestedRange, revision, enabled], scheduleLoad, {
    deep: true,
    immediate: true,
  });

  watch(
    dataSource,
    (source) => {
      unsubscribe?.();
      unsubscribe =
        source?.subscribeInvalidations((event) => {
          revision.value = Math.max(revision.value, event.revision);
        }) ?? null;
    },
    { immediate: true },
  );

  onScopeDispose(() => {
    requestSequence += 1;
    if (loadTimer !== null) clearTimeout(loadTimer);
    unsubscribe?.();
  });

  return {
    window: computed(() => window.value),
    isPending,
    error,
  };
}
