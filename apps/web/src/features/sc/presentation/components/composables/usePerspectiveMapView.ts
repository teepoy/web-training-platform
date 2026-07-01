import { ref, watch, onUnmounted, type ComputedRef, type Ref } from "vue";
import type { Table, Filter } from "@perspective-dev/client";
import {
  managePerspectiveTable,
  type ManagedPerspectiveView,
} from "@/features/sc/presentation/composables/managedPerspectiveView";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyViewConfig = any;

export interface MapBinRow {
  gx: number;
  gy: number;
  binSize: number;
  count: number;
  map_in_selection: number;
  images_has_review: number;
  gallery_in_selection: number;
  _legendCol: string;
  [legendCol: string]: number | string;
}

export interface MapViewport {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface PerspectiveMapViewState {
  waferRows: Ref<MapBinRow[] | null>;
  dieRows: Ref<MapBinRow[] | null>;
  reticleRows: Ref<MapBinRow[] | null>;
  pending: Ref<boolean>;
  error: Ref<string | null>;
}

interface PerspectiveUpdateEvent {
  port_id?: unknown;
}

const MODES = ["wafer", "die", "reticle"] as const;
type MapMode = (typeof MODES)[number];

interface ModeConfig {
  xCol: string;
  yCol: string;
  fullRangeNm: number;
  fullBins: number;
}

const MODE_CONFIGS: Record<MapMode, ModeConfig> = {
  wafer: { xCol: "wafer_x", yCol: "wafer_y", fullRangeNm: 300_000_000, fullBins: 600 },
  die: { xCol: "die_x", yCol: "die_y", fullRangeNm: 100_000, fullBins: 200 },
  reticle: { xCol: "reticle_x", yCol: "reticle_y", fullRangeNm: 200_000, fullBins: 200 },
};

interface ModeUpdateContext {
  view: ManagedPerspectiveView | null;
  binSize: number;
  isZoom: boolean;
  col: string;
  xCol: string;
}

function eventPortId(evt: unknown): number | null {
  if (!evt || typeof evt !== "object") return null;
  const portId = (evt as PerspectiveUpdateEvent).port_id;
  return typeof portId === "number" ? portId : null;
}

function retireView(v: ManagedPerspectiveView | null): void {
  if (!v) return;
  window.setTimeout(() => v.retire(), 1000);
}

const BIN_RESOLUTION: Record<MapMode, { large: number; small: number }> = {
  wafer: { large: 600, small: 400 },
  die: { large: 600, small: 400 },
  reticle: { large: 600, small: 400 },
};

function unzoomBinSize(mode: MapMode, dims: { w: number; h: number }): number {
  const cfg = MODE_CONFIGS[mode];
  const res = BIN_RESOLUTION[mode];
  const minDim = Math.min(dims.w, dims.h);
  const bins = minDim < 500 ? res.small : res.large;
  return cfg.fullRangeNm / bins;
}

export function usePerspectiveMapView(
  table: Ref<Table | null>,
  zoomByMode: Ref<Record<(typeof MODES)[number], MapViewport | null>>,
  globalFilters: Ref<Filter[]>,
  hiddenLegendKeys: Ref<string[]>,
  legendCol: Ref<string>,
  canvasDims: Ref<{ w: number; h: number }>,
  enabledModes: MapMode[] = ["wafer", "die", "reticle"],
  activeMapMode?: Ref<MapMode> | ComputedRef<MapMode>,
  ignoredUpdatePorts?: Ref<readonly number[]> | ComputedRef<readonly number[]>,
  onRecoverableError?: (reason: string, err: unknown) => void,
): PerspectiveMapViewState {
  const waferRows = ref<MapBinRow[] | null>(null);
  const dieRows = ref<MapBinRow[] | null>(null);
  const reticleRows = ref<MapBinRow[] | null>(null);
  const pending = ref(false);
  const error = ref<string | null>(null);

  function rowsRefForMode(mode: MapMode): Ref<MapBinRow[] | null> {
    switch (mode) {
      case "wafer":
        return waferRows;
      case "die":
        return dieRows;
      case "reticle":
        return reticleRows;
    }
  }

  const waferVersion = ref(0);
  const dieVersion = ref(0);
  const reticleVersion = ref(0);

  let activeView: ManagedPerspectiveView | null = null;
  let activeViewMode: MapMode | null = null;

  // Cache unzoomed (zoom=null) views per mode — keyed by filter/col/dims hash
  const _uzCache: Record<
    MapMode,
    { rows: MapBinRow[]; binSize: number; col: string; xCol: string } | null
  > = {
    wafer: null,
    die: null,
    reticle: null,
  };
  const modeContexts: Record<MapMode, ModeUpdateContext> = {
    wafer: { view: null, binSize: 0, isZoom: false, col: "", xCol: "" },
    die: { view: null, binSize: 0, isZoom: false, col: "", xCol: "" },
    reticle: { view: null, binSize: 0, isZoom: false, col: "", xCol: "" },
  };
  let _uzCacheKey = "";

  let _rebuildSeq = 0;
  let _activeTable: Table | null = null;

  function clearViews(): void {
    _rebuildSeq += 1;
    activeView?.retire();
    activeView = null;
    activeViewMode = null;
    for (const mode of MODES) {
      _uzCache[mode] = null;
      modeContexts[mode] = { view: null, binSize: 0, isZoom: false, col: "", xCol: "" };
    }
    _uzCacheKey = "";
  }

  function _computeRowData(
    data: Record<string, unknown[]>,
    binSize: number,
    isZoom: boolean,
    mode: MapMode,
    col: string,
    xCol: string,
  ): MapBinRow[] {
    const gxArr = data.gx as number[] | undefined;
    const legendArr = data[col] as (number | string)[] | undefined;
    const countArr = data[xCol] as number[] | undefined;
    const inSelArr = data.map_in_selection as number[] | undefined;
    const imagesArr = data.images as number[] | undefined;
    const gallerySelArr = data.gallery_in_selection as number[] | undefined;
    const rowPaths = data.__ROW_PATH__ as unknown[][] | undefined;
    if (!gxArr || !rowPaths || !legendArr || !countArr) {
      throw new Error(
        `[psp-map:${mode}] unexpected to_columns keys: ${Object.keys(data).join(", ")}`,
      );
    }
    const resultRows: MapBinRow[] = [];
    for (let i = 0; i < gxArr.length; i++) {
      if (!rowPaths[i] || rowPaths[i].length !== 2) continue;
      const r: MapBinRow = {
        gx: Number(rowPaths[i][0]),
        gy: Number(rowPaths[i][1]),
        binSize,
        count: countArr[i] ?? 1,
        map_in_selection: inSelArr?.[i] ? 1 : 0,
        images_has_review: (imagesArr?.[i] ?? 0) > 0 ? 1 : 0,
        gallery_in_selection: gallerySelArr?.[i] ? 1 : 0,
        _legendCol: col,
      };
      r[col] = legendArr[i];
      resultRows.push(r);
    }
    return resultRows;
  }

  function shouldProcessUpdate(mode: MapMode, evt: unknown): boolean {
    if (activeMapMode && activeMapMode.value !== mode) return false;
    const portId = eventPortId(evt);
    if (portId == null) return true;
    return !(ignoredUpdatePorts?.value ?? []).includes(portId);
  }

  function incrementModeVersion(mode: MapMode): void {
    switch (mode) {
      case "wafer":
        waferVersion.value++;
        break;
      case "die":
        dieVersion.value++;
        break;
      case "reticle":
        reticleVersion.value++;
        break;
    }
    console.debug("[map-view] incrementModeVersion", {
      mode,
      waferVersion: waferVersion.value,
      dieVersion: dieVersion.value,
      reticleVersion: reticleVersion.value,
    });
  }

  async function rebuildMode(mode: MapMode): Promise<void> {
    const tbl = table.value;
    if (!tbl) return;

    const cfg = MODE_CONFIGS[mode];
    const zoomVp = zoomByMode.value[mode];
    const col = legendCol.value;
    const buildSeq = _rebuildSeq;

    let binSize: number;
    let isZoom = false;
    let hasDisplayCache = false;
    const extraFilters: Filter[] = [];

    if (zoomVp && canvasDims.value.w > 0) {
      isZoom = true;
      binSize = zoomVp.w / canvasDims.value.w;
      extraFilters.push(
        [cfg.xCol, ">=", zoomVp.x] as Filter,
        [cfg.xCol, "<=", zoomVp.x + zoomVp.w] as Filter,
        [cfg.yCol, ">=", zoomVp.y] as Filter,
        [cfg.yCol, "<=", zoomVp.y + zoomVp.h] as Filter,
      );
    } else {
      binSize = unzoomBinSize(mode, canvasDims.value);

      // Unzoomed cache is display-only. The active mode still rebuilds one live
      // view so on_update remains attached only to the visible map.
      if (_uzCache[mode]) {
        const cached = _uzCache[mode]!;
        rowsRefForMode(mode).value = cached.rows;
        hasDisplayCache = true;
      }
    }
    if (!hasDisplayCache) {
      rowsRefForMode(mode).value = null;
    }

    const allFilters = [...globalFilters.value, ...extraFilters];
    if (hiddenLegendKeys.value.length > 0) {
      allFilters.push([col, "not in", hiddenLegendKeys.value] as Filter);
    }
    const exprGx = `floor("${cfg.xCol}" / ${binSize})`;
    const exprGy = `floor("${cfg.yCol}" / ${binSize})`;

    const vCfg: Record<string, unknown> = {
      expressions: { gx: exprGx, gy: exprGy },
      columns: ["gx", "gy", col, cfg.xCol, "map_in_selection", "images", "gallery_in_selection"],
      group_by: ["gx", "gy"],
      aggregates: {
        [col]: "last",
        [cfg.xCol]: "count",
        map_in_selection: "max",
        images: "max",
        gallery_in_selection: "max",
      } as Record<string, string>,
      filter: allFilters.length > 0 ? allFilters : undefined,
    };

    const managedTable = managePerspectiveTable(tbl);
    const managed = await managedTable.view(vCfg as AnyViewConfig);
    if (_rebuildSeq !== buildSeq || (activeMapMode && activeMapMode.value !== mode)) {
      managed.retire();
      return;
    }
    const previousActiveView = activeView;
    activeView = managed;
    activeViewMode = mode;
    retireView(previousActiveView);

    modeContexts[mode] = { view: managed, binSize, isZoom, col, xCol: cfg.xCol };

    managed.onUpdateDebounced(
      (evt: unknown) => {
        incrementModeVersion(mode);
      },
      {
        shouldRun: (evt) => shouldProcessUpdate(mode, evt),
      },
    );

    const nr = await managed.num_rows();
    if (activeView !== managed || activeViewMode !== mode || _rebuildSeq !== buildSeq) {
      managed.retire();
      return;
    }
    if (nr === 0) {
      rowsRefForMode(mode).value = [];
      if (!isZoom) {
        _uzCache[mode] = { rows: [], binSize, col, xCol: cfg.xCol };
      }
      return;
    }
    console.time("view.to_columns:rebuild");
    const data = (await managed.to_columns()) as Record<string, unknown[]>;
    console.timeEnd("view.to_columns:rebuild");
    if (activeView !== managed || activeViewMode !== mode || _rebuildSeq !== buildSeq) {
      managed.retire();
      return;
    }

    const resultRows = _computeRowData(data, binSize, isZoom, mode, col, cfg.xCol);
    rowsRefForMode(mode).value = resultRows;

    // Save unzoomed result to cache
    if (!isZoom) {
      _uzCache[mode] = { rows: resultRows, binSize, col, xCol: cfg.xCol };
    }
  }

  watch(
    () => waferVersion.value,
    async () => {
      console.debug("[map-view] wafer version watcher", { version: waferVersion.value });
      const ctx = modeContexts.wafer;
      if (!ctx.view) return;
      try {
        const nr = await ctx.view.num_rows();
        if (nr === 0) {
          waferRows.value = [];
          if (!ctx.isZoom)
            _uzCache.wafer = {
              rows: [],
              binSize: ctx.binSize,
              col: ctx.col,
              xCol: ctx.xCol,
            };
          return;
        }
        // console.time("view.to_columns:wafer1");
        // const data0 = await managed.to_arrow();
        // console.timeEnd("view.to_columns:wafer1");

        console.time("view.to_columns:wafer");
        const data = (await ctx.view.to_columns()) as Record<string, unknown[]>;
        waferRows.value = _computeRowData(
          data,
          ctx.binSize,
          ctx.isZoom,
          "wafer",
          ctx.col,
          ctx.xCol,
        );
        console.timeEnd("view.to_columns:wafer");

        if (!ctx.isZoom)
          _uzCache.wafer = {
            rows: waferRows.value!,
            binSize: ctx.binSize,
            col: ctx.col,
            xCol: ctx.xCol,
          };
      } catch (e) {
        console.error("[psp-map:wafer] on_update ERROR:", e);
        onRecoverableError?.("wafer map update failed", e);
      }
    },
  );

  watch(
    () => dieVersion.value,
    async () => {
      console.debug("[map-view] die version watcher", { version: dieVersion.value });
      const ctx = modeContexts.die;
      if (!ctx.view) return;
      try {
        const nr = await ctx.view.num_rows();
        if (nr === 0) {
          dieRows.value = [];
          if (!ctx.isZoom)
            _uzCache.die = {
              rows: [],
              binSize: ctx.binSize,
              col: ctx.col,
              xCol: ctx.xCol,
            };
          return;
        }
        console.time("view.to_columns:die");
        const data = (await ctx.view.to_columns()) as Record<string, unknown[]>;
        console.timeEnd("view.to_columns:die");
        dieRows.value = _computeRowData(data, ctx.binSize, ctx.isZoom, "die", ctx.col, ctx.xCol);
        if (!ctx.isZoom)
          _uzCache.die = {
            rows: dieRows.value!,
            binSize: ctx.binSize,
            col: ctx.col,
            xCol: ctx.xCol,
          };
      } catch (e) {
        console.error("[psp-map:die] on_update ERROR:", e);
        onRecoverableError?.("die map update failed", e);
      }
    },
  );

  watch(
    () => reticleVersion.value,
    async () => {
      console.debug("[map-view] reticle version watcher", { version: reticleVersion.value });
      const ctx = modeContexts.reticle;
      if (!ctx.view) return;
      try {
        const nr = await ctx.view.num_rows();
        if (nr === 0) {
          reticleRows.value = [];
          if (!ctx.isZoom)
            _uzCache.reticle = {
              rows: [],
              binSize: ctx.binSize,
              col: ctx.col,
              xCol: ctx.xCol,
            };
          return;
        }
        console.time("view.to_columns:reticle");
        const data = (await ctx.view.to_columns()) as Record<string, unknown[]>;
        console.timeEnd("view.to_columns:reticle");
        reticleRows.value = _computeRowData(
          data,
          ctx.binSize,
          ctx.isZoom,
          "reticle",
          ctx.col,
          ctx.xCol,
        );
        if (!ctx.isZoom)
          _uzCache.reticle = {
            rows: reticleRows.value!,
            binSize: ctx.binSize,
            col: ctx.col,
            xCol: ctx.xCol,
          };
      } catch (e) {
        console.error("[psp-map:reticle] on_update ERROR:", e);
        onRecoverableError?.("reticle map update failed", e);
      }
    },
  );

  async function rebuildAll(): Promise<void> {
    if (table.value !== _activeTable) {
      _activeTable = table.value;
      clearViews();
    }

    if (!table.value) {
      waferRows.value = null;
      dieRows.value = null;
      reticleRows.value = null;
      pending.value = false;
      return;
    }

    const seq = ++_rebuildSeq;

    // Invalidate unzoomed cache when filter/legend state changes
    const cacheKey = JSON.stringify({
      f: globalFilters.value,
      h: hiddenLegendKeys.value,
      c: legendCol.value,
      d: canvasDims.value,
    });
    if (cacheKey !== _uzCacheKey) {
      _uzCacheKey = cacheKey;
      for (const m of MODES) {
        _uzCache[m] = null;
      }
    }

    pending.value = true;

    const mode = activeMapMode?.value ?? enabledModes[0];
    if (!enabledModes.includes(mode)) {
      pending.value = false;
      return;
    }
    try {
      await rebuildMode(mode);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error(`[psp-map:${mode}] ERROR:`, msg);
      error.value = `[${mode}] ${msg}`;
      onRecoverableError?.(`${mode} map rebuild failed`, e);
    }

    if (_rebuildSeq === seq) {
      pending.value = false;
    }
  }

  watch(
    [
      () => table.value,
      () => globalFilters.value,
      () => hiddenLegendKeys.value,
      () => legendCol.value,
      () => zoomByMode.value,
      () => canvasDims.value,
      () => activeMapMode?.value,
    ],
    () => {
      rebuildAll();
    },
    { immediate: true },
  );

  onUnmounted(() => {
    clearViews();
  });

  return { waferRows, dieRows, reticleRows, pending, error };
}
