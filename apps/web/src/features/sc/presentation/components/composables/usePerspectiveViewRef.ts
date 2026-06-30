import { computed, ref, shallowRef, watch, onUnmounted, type Ref } from "vue";
import type { Table, View, ViewConfigUpdate } from "@perspective-dev/client";

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

function onPerspectiveUpdate(v: View, cb: (evt: unknown) => void): void {
  v.on_update(cb);
}

export function usePerspectiveViewRef(
  table: Ref<Table | null>,
  config: Ref<ViewConfig>,
  opts?: { onChange?: () => void; onRecoverableError?: (reason: string, err: unknown) => void },
): {
  view: Ref<View | null>;
  pending: Ref<boolean>;
  error: Ref<string | null>;
  version: Ref<number>;
  latestTiming: Ref<PerspectiveViewTiming | null>;
} {
  const view = shallowRef<View | null>(null);
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

  function retireView(v: View | null): void {
    if (!v || retiredViews.has(v)) return;
    retiredViews.add(v);
    window.setTimeout(() => {
      try {
        v.delete();
      } catch {
        /* best effort */
      } finally {
        retiredViews.delete(v);
      }
    }, 1000);
  }

  async function rebuild(tbl: Table, cfg: ViewConfig): Promise<void> {
    const seq = ++rebuildSeq;
    const t0 = performance.now();

    pending.value = true;
    error.value = null;

    try {
      const previousView = view.value;
      const v = await tbl.view(cfg);
      const viewMs = performance.now() - t0;
      if (seq !== rebuildSeq) {
        v.delete();
        return;
      }

      const tRows = performance.now();
      const nr = await v.num_rows();
      const rowsMs = performance.now() - tRows;
      if (seq !== rebuildSeq) {
        v.delete();
        return;
      }

      view.value = v;
      retireView(previousView);
      onPerspectiveUpdate(v, (_evt: unknown) => {
        if (view.value !== v) return;
        console.log("[view] onPerspectiveUpdate → notifyChanged, delta:", (_evt as any).delta);
        notifyChanged();
      });
      console.log("[view] rebuild done", { viewMs, rowsMs, nr, cfg });
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
    for (const v of [activeView, ...retiredViews]) {
      if (v) {
        try {
          v.delete();
        } catch {
          /* best effort */
        }
      }
    }
    retiredViews.clear();
  });

  return { view, pending, error, version, latestTiming };
}
