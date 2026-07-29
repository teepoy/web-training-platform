import { computed, ref, shallowRef, watch, onUnmounted, type Ref, type ShallowRef } from "vue";
import type { Table, View } from "@perspective-dev/client";
import {
  managePerspectiveTable,
  type ManagedPerspectiveView,
  retirePerspectiveView,
} from "@/features/sc/presentation/composables/managedPerspectiveView";
import {
  perspectiveViewConfigKey,
  type PerspectiveViewConfig,
} from "@/features/sc/presentation/composables/perspectiveViewConfig";

/**
 * Reactive publication of a mutable Perspective View.
 *
 * Perspective updates a View in place, so `view` keeps the same identity.
 * Publishing a new snapshot lets Vue consumers react to changed data without
 * passing a separate revision prop that can drift out of sync with the View.
 */
export interface PerspectiveViewSnapshot {
  readonly view: ManagedPerspectiveView;
  readonly viewConfigKey: string;
}

export interface PerspectiveViewBuildTiming {
  label: string;
  viewMs: number;
  rowsMs: number;
  rows: number;
  columns: number | string;
}

export function useManagedPerspectiveView(
  perspectiveTable: Ref<Table | null>,
  viewConfig: Ref<PerspectiveViewConfig>,
  options?: { onRecoverableError?: (reason: string, err: unknown) => void },
): {
  snapshot: ShallowRef<PerspectiveViewSnapshot | null>;
  isPending: Ref<boolean>;
  errorMessage: Ref<string | null>;
  latestBuildTiming: Ref<PerspectiveViewBuildTiming | null>;
} {
  const snapshot = shallowRef<PerspectiveViewSnapshot | null>(null);
  const isPending = ref(false);
  const errorMessage = ref<string | null>(null);
  const latestBuildTiming = ref<PerspectiveViewBuildTiming | null>(null);
  const onRecoverableError = options?.onRecoverableError;

  const configKey = computed(() => perspectiveViewConfigKey(viewConfig.value));
  let activeView: ManagedPerspectiveView | null = null;
  let activeViewConfigKey = "";
  let rebuildSeq = 0;
  let publishQueued = false;
  const retiredViews = new Set<View>();

  function publishSnapshot(): void {
    if (publishQueued) return;
    publishQueued = true;
    queueMicrotask(() => {
      publishQueued = false;
      const view = activeView;
      if (!view) {
        snapshot.value = null;
        return;
      }
      snapshot.value = {
        view,
        viewConfigKey: activeViewConfigKey,
      };
    });
  }

  function retireView(v: ManagedPerspectiveView | null): void {
    if (!v || retiredViews.has(v.rawView)) return;
    retiredViews.add(v.rawView);
    window.setTimeout(() => {
      v.retire();
      retiredViews.delete(v.rawView);
    }, 1000);
  }

  async function rebuild(table: Table, config: PerspectiveViewConfig, key: string): Promise<void> {
    const seq = ++rebuildSeq;
    const t0 = performance.now();

    isPending.value = true;
    errorMessage.value = null;

    try {
      const previousView = activeView;
      const managedTable = managePerspectiveTable(table);
      const managed = await managedTable.view(config);
      const viewMs = performance.now() - t0;
      if (seq !== rebuildSeq) {
        managed.retire();
        return;
      }

      const tRows = performance.now();
      const nr = await managed.num_rows();
      const rowsMs = performance.now() - tRows;
      if (seq !== rebuildSeq) {
        managed.retire();
        return;
      }

      activeView = managed;
      activeViewConfigKey = key;
      retireView(previousView);
      managed.onUpdateDebounced((_evt: unknown) => {
        if (activeView !== managed) return;
        publishSnapshot();
      });
      publishSnapshot();
      latestBuildTiming.value = {
        label: `cols=${config.columns?.length ?? "all"} filter=${config.filter?.length ?? 0} gb=${config.group_by?.length ?? 0}`,
        viewMs,
        rowsMs,
        rows: nr,
        columns: config.columns?.length ?? "all",
      };
    } catch (e: unknown) {
      if (seq !== rebuildSeq) return;
      const msg = e instanceof Error ? e.message : String(e);
      errorMessage.value = msg;
      onRecoverableError?.("view rebuild failed", e);
    } finally {
      if (seq === rebuildSeq) isPending.value = false;
    }
  }

  watch(
    [() => perspectiveTable.value, () => configKey.value],
    ([table, key]) => {
      if (!table) {
        rebuildSeq += 1;
        isPending.value = false;
        retireView(activeView);
        activeView = null;
        activeViewConfigKey = "";
        publishSnapshot();
        return;
      }
      void rebuild(table, viewConfig.value, key);
    },
    { immediate: true },
  );

  onUnmounted(() => {
    rebuildSeq += 1;
    const view = activeView;
    activeView = null;
    snapshot.value = null;
    view?.retire();
    for (const v of retiredViews) {
      retirePerspectiveView(v);
    }
    retiredViews.clear();
  });

  return { snapshot, isPending, errorMessage, latestBuildTiming };
}
