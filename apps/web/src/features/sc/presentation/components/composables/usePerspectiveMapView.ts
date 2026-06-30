import { ref, watch, onUnmounted, type ComputedRef, type Ref } from "vue";
import type { Table, View, Filter } from "@perspective-dev/client";

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
  view: View | null;
  binSize: number;
  isZoom: boolean;
  col: string;
  xCol: string;
}

function onPerspectiveUpdate(v: View, cb: (evt: unknown) => void): void {
  v.on_update(cb);
}

function eventPortId(evt: unknown): number | null {
  if (!evt || typeof evt !== "object") return null;
  const portId = (evt as PerspectiveUpdateEvent).port_id;
  return typeof portId === "number" ? portId : null;
}

function retireView(v: View | null): void {
  if (!v) return;
  window.setTimeout(() => {
    try {
      v.delete();
    } catch {
      /* ignore */
    }
  }, 1000);
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
): PerspectiveMapViewState {
  const waferRows = ref<MapBinRow[] | null>(null);
  const dieRows = ref<MapBinRow[] | null>(null);
  const reticleRows = ref<MapBinRow[] | null>(null);
  const pending = ref(false);
  const error = ref<string | null>(null);

  const waferVersion = ref(0);
  const dieVersion = ref(0);
  const reticleVersion = ref(0);

  const views: Record<MapMode, View | null> = {
    wafer: null,
    die: null,
    reticle: null,
  };

  // Cache unzoomed (zoom=null) views per mode — keyed by filter/col/dims hash
  const _uzCache: Record<
    MapMode,
    { rows: MapBinRow[]; view: View; binSize: number; col: string; xCol: string } | null
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

      // Unzoomed — check cache
      if (_uzCache[mode]) {
        const cached = _uzCache[mode]!;
        const previous = views[mode];
        views[mode] = null;
        retireView(previous);
        modeContexts[mode] = {
          view: cached.view,
          binSize: cached.binSize,
          isZoom: false,
          col: cached.col,
          xCol: cached.xCol,
        };
        switch (mode) {
          case "wafer":
            waferRows.value = cached.rows;
            break;
          case "die":
            dieRows.value = cached.rows;
            break;
          case "reticle":
            reticleRows.value = cached.rows;
            break;
        }
        return;
      }
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

    const v = (await tbl.view(vCfg as AnyViewConfig)) as View;

    modeContexts[mode] = { view: v, binSize, isZoom, col, xCol: cfg.xCol };

    onPerspectiveUpdate(v, (evt: unknown) => {
      console.debug("[map-view] onPerspectiveUpdate", { mode, portId: eventPortId(evt) });
      if (!shouldProcessUpdate(mode, evt)) return;
      incrementModeVersion(mode);
    });

    // Only store non-zoomed views in the persistent slot; zoomed views replace the old zoomed one
    if (isZoom) {
      const previous = views[mode];
      views[mode] = v;
      retireView(previous);
    }

    const nr = await v.num_rows();
    if ((isZoom && views[mode] !== v) || (!isZoom && _rebuildSeq !== buildSeq)) return;
    if (nr === 0) {
      switch (mode) {
        case "wafer":
          waferRows.value = [];
          break;
        case "die":
          dieRows.value = [];
          break;
        case "reticle":
          reticleRows.value = [];
          break;
      }
      if (!isZoom) {
        _uzCache[mode] = { rows: [], view: v, binSize, col, xCol: cfg.xCol };
      }
      return;
    }
    const data = (await v.to_columns()) as Record<string, unknown[]>;
    if ((isZoom && views[mode] !== v) || (!isZoom && _rebuildSeq !== buildSeq)) return;

    const resultRows = _computeRowData(data, binSize, isZoom, mode, col, cfg.xCol);

    switch (mode) {
      case "wafer":
        waferRows.value = resultRows;
        break;
      case "die":
        dieRows.value = resultRows;
        break;
      case "reticle":
        reticleRows.value = resultRows;
        break;
    }

    // Save unzoomed result to cache
    if (!isZoom) {
      _uzCache[mode] = { rows: resultRows, view: v, binSize, col, xCol: cfg.xCol };
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
              view: ctx.view,
              binSize: ctx.binSize,
              col: ctx.col,
              xCol: ctx.xCol,
            };
          return;
        }
        const data = (await ctx.view.to_columns()) as Record<string, unknown[]>;
        waferRows.value = _computeRowData(
          data,
          ctx.binSize,
          ctx.isZoom,
          "wafer",
          ctx.col,
          ctx.xCol,
        );
        if (!ctx.isZoom)
          _uzCache.wafer = {
            rows: waferRows.value!,
            view: ctx.view,
            binSize: ctx.binSize,
            col: ctx.col,
            xCol: ctx.xCol,
          };
      } catch (e) {
        console.error("[psp-map:wafer] on_update ERROR:", e);
      }
    },
  );

  watch(
    () => activeMapMode?.value,
    (mode) => {
      if (!mode) return;
      incrementModeVersion(mode);
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
              view: ctx.view,
              binSize: ctx.binSize,
              col: ctx.col,
              xCol: ctx.xCol,
            };
          return;
        }
        const data = (await ctx.view.to_columns()) as Record<string, unknown[]>;
        dieRows.value = _computeRowData(data, ctx.binSize, ctx.isZoom, "die", ctx.col, ctx.xCol);
        if (!ctx.isZoom)
          _uzCache.die = {
            rows: dieRows.value!,
            view: ctx.view,
            binSize: ctx.binSize,
            col: ctx.col,
            xCol: ctx.xCol,
          };
      } catch (e) {
        console.error("[psp-map:die] on_update ERROR:", e);
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
              view: ctx.view,
              binSize: ctx.binSize,
              col: ctx.col,
              xCol: ctx.xCol,
            };
          return;
        }
        const data = (await ctx.view.to_columns()) as Record<string, unknown[]>;
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
            view: ctx.view,
            binSize: ctx.binSize,
            col: ctx.col,
            xCol: ctx.xCol,
          };
      } catch (e) {
        console.error("[psp-map:reticle] on_update ERROR:", e);
      }
    },
  );

  async function rebuildAll(): Promise<void> {
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
        if (_uzCache[m]) {
          retireView(_uzCache[m]!.view);
          _uzCache[m] = null;
        }
      }
    }

    pending.value = true;

    for (const mode of enabledModes) {
      if (_rebuildSeq !== seq) {
        return;
      }
      try {
        await rebuildMode(mode);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        console.error(`[psp-map:${mode}] ERROR:`, msg);
        error.value = `[${mode}] ${msg}`;
      }
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
    ],
    () => {
      rebuildAll();
    },
    { immediate: true },
  );

  onUnmounted(() => {
    for (const mode of MODES) {
      if (views[mode]) {
        try {
          views[mode].delete();
        } catch {
          /* ignore */
        }
        views[mode] = null;
      }
      if (_uzCache[mode]) {
        try {
          _uzCache[mode]!.view.delete();
        } catch {
          /* ignore */
        }
        _uzCache[mode] = null;
      }
    }
  });

  return { waferRows, dieRows, reticleRows, pending, error };
}
