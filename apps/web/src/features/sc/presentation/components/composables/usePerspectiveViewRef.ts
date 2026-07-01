import { computed, ref, shallowRef, watch, onUnmounted, type Ref } from "vue";
import type { Table, View, ViewConfigUpdate } from "@perspective-dev/client";
import {
  managePerspectiveTable,
  type ManagedPerspectiveView,
  retirePerspectiveView,
} from "@/features/sc/presentation/composables/managedPerspectiveView";

export type ViewConfig = ViewConfigUpdate;

export interface PerspectiveViewTiming {
  label: string;
  viewMs: number;
  rowsMs: number;
  rows: number;
  columns: number | string;
}

function viewConfigKey(cfg: ViewConfig): string {
  return JSON.stringify({
    cols: cfg.columns,
    expr: cfg.expressions,
    filt: cfg.filter,
    sort: cfg.sort,
    gby: cfg.group_by,
    agg: cfg.aggregates,
  });
}

export function usePerspectiveViewRef(
  table: Ref<Table | null>,
  config: Ref<ViewConfig>,
  opts?: { onChange?: () => void; onRecoverableError?: (reason: string, err: unknown) => void },
): {
  view: Ref<ManagedPerspectiveView | null>;
  pending: Ref<boolean>;
  error: Ref<string | null>;
  version: Ref<number>;
  latestTiming: Ref<PerspectiveViewTiming | null>;
} {
  const view = shallowRef<ManagedPerspectiveView | null>(null);
  const pending = ref(false);
  const error = ref<string | null>(null);
  const version = ref(0);
  const onChange = opts?.onChange;
  const latestTiming = ref<PerspectiveViewTiming | null>(null);
  const onRecoverableError = opts?.onRecoverableError;

  const configKey = computed(() => viewConfigKey(config.value));
  let rebuildSeq = 0;
  let notifyQueued = false;
  const retiredViews = new Set<View>();

  function notifyChanged(): void {
    if (notifyQueued) return;
    notifyQueued = true;
    queueMicrotask(() => {
      notifyQueued = false;
      version.value += 1;
      console.debug("[view] version bump", { version: version.value });
      onChange?.();
    });
  }

  function retireView(v: ManagedPerspectiveView | null): void {
    if (!v || retiredViews.has(v.view)) return;
    retiredViews.add(v.view);
    window.setTimeout(() => {
      v.retire();
      retiredViews.delete(v.view);
    }, 1000);
  }

  async function rebuild(tbl: Table, cfg: ViewConfig): Promise<void> {
    const seq = ++rebuildSeq;
    const t0 = performance.now();

    pending.value = true;
    error.value = null;

    try {
      const previousView = view.value;
      const managedTable = managePerspectiveTable(tbl);
      const managed = await managedTable.view(cfg);
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

      view.value = managed;
      retireView(previousView);
      managed.onUpdateDebounced((_evt: unknown) => {
        if (view.value !== managed) return;
        notifyChanged();
      });
      notifyChanged();
      latestTiming.value = {
        label: `cols=${cfg.columns?.length ?? "all"} filter=${cfg.filter?.length ?? 0} gb=${cfg.group_by?.length ?? 0}`,
        viewMs,
        rowsMs,
        rows: nr,
        columns: cfg.columns?.length ?? "all",
      };
    } catch (e: unknown) {
      if (seq !== rebuildSeq) return;
      const msg = e instanceof Error ? e.message : String(e);
      error.value = msg;
      onRecoverableError?.("view rebuild failed", e);
    } finally {
      if (seq === rebuildSeq) pending.value = false;
    }
  }

  watch(
    [() => table.value, () => configKey.value],
    ([tbl]) => {
      if (!tbl) {
        rebuildSeq += 1;
        pending.value = false;
        retireView(view.value);
        view.value = null;
        return;
      }
      void rebuild(tbl, config.value);
    },
    { immediate: true },
  );

  onUnmounted(() => {
    rebuildSeq += 1;
    const activeView = view.value;
    view.value = null;
    activeView?.retire();
    for (const v of retiredViews) {
      retirePerspectiveView(v);
    }
    retiredViews.clear();
  });

  return { view, pending, error, version, latestTiming };
}
