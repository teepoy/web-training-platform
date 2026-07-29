import { onScopeDispose, ref, shallowRef, watch, type Ref, type ShallowRef } from "vue";
import type { PerspectiveViewSnapshot } from "./useManagedPerspectiveView";

export interface GallerySampleRange {
  start: number;
  end: number;
}

export interface PagedGalleryWindow<T> {
  items: T[];
  offset: number;
  total: number;
}

export interface PagedPerspectiveGalleryState<T> {
  window: ShallowRef<PagedGalleryWindow<T>>;
  isPending: Ref<boolean>;
  errorMessage: Ref<string | null>;
}

const DEFAULT_PAGE_SIZE = 1_000;
const DEFAULT_WINDOW_PAGES = 2;

function emptyWindow<T>(): PagedGalleryWindow<T> {
  return { items: [], offset: 0, total: 0 };
}

export function usePagedPerspectiveGallery<T>(
  snapshot: Ref<PerspectiveViewSnapshot | null>,
  requestedRange: Ref<GallerySampleRange>,
  parseItems: (ipc: unknown, offset: number) => T[],
  options: {
    pageSize?: number;
    windowPages?: number;
    onRecoverableError?: (reason: string, error: unknown) => void;
  } = {},
): PagedPerspectiveGalleryState<T> {
  const pageSize = options.pageSize ?? DEFAULT_PAGE_SIZE;
  const windowSize = pageSize * (options.windowPages ?? DEFAULT_WINDOW_PAGES);
  const window = shallowRef<PagedGalleryWindow<T>>(emptyWindow());
  const isPending = ref(false);
  const errorMessage = ref<string | null>(null);
  let requestSequence = 0;
  let loadedSnapshot: PerspectiveViewSnapshot | null = null;

  function coversRange(current: PagedGalleryWindow<T>, range: GallerySampleRange): boolean {
    if (current.total === 0) return true;
    return range.start >= current.offset && range.end <= current.offset + current.items.length;
  }

  async function load(
    nextSnapshot: PerspectiveViewSnapshot,
    range: GallerySampleRange,
  ): Promise<void> {
    if (loadedSnapshot === nextSnapshot && coversRange(window.value, range)) return;

    const sequence = ++requestSequence;
    isPending.value = true;
    errorMessage.value = null;
    try {
      const total = await nextSnapshot.view.num_rows();
      if (sequence !== requestSequence || snapshot.value !== nextSnapshot) return;
      if (total === 0) {
        loadedSnapshot = nextSnapshot;
        window.value = emptyWindow();
        return;
      }

      const target = Math.max(0, Math.min(range.start, total - 1));
      const maxOffset = Math.max(0, total - windowSize);
      const offset = Math.min(Math.floor(target / pageSize) * pageSize, maxOffset);

      const ipc = await nextSnapshot.view.to_arrow({
        start_row: offset,
        end_row: Math.min(total, offset + windowSize),
      });
      if (sequence !== requestSequence || snapshot.value !== nextSnapshot) return;

      const items = parseItems(ipc, offset);
      loadedSnapshot = nextSnapshot;
      window.value = { items, offset, total };
    } catch (error) {
      if (sequence !== requestSequence) return;
      errorMessage.value = error instanceof Error ? error.message : String(error);
      options.onRecoverableError?.("gallery window load failed", error);
    } finally {
      if (sequence === requestSequence) isPending.value = false;
    }
  }

  watch(
    [() => snapshot.value, () => requestedRange.value.start, () => requestedRange.value.end],
    ([nextSnapshot, start, end]) => {
      if (!nextSnapshot) {
        requestSequence += 1;
        loadedSnapshot = null;
        isPending.value = window.value.total > 0;
        errorMessage.value = null;
        return;
      }
      void load(nextSnapshot, { start, end });
    },
    { immediate: true },
  );

  onScopeDispose(() => {
    requestSequence += 1;
  });

  return { window, isPending, errorMessage };
}
