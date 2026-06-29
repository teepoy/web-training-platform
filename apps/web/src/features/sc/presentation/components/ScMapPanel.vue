<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  NTabs,
  NTabPane,
  NResult,
  NButton,
  NSelect,
  NIcon,
  NTooltip,
  NProgress,
  NText,
} from "naive-ui";
import { ArrowBackOutline, ArrowForwardOutline } from "@vicons/ionicons5";
import { AddOutline, ScanOutline, SearchOutline } from "@vicons/ionicons5";
import ScWaferMap from "./ScWaferMap.vue";
import ScDieStackMap from "./ScDieStackMap.vue";
import ScReticleMap from "./ScReticleMap.vue";
import ScLegend from "./ScLegend.vue";
import ScReticleMapOptionsButton from "./ScReticleMapOptionsButton.vue";
import { legendColor, parsePoints, STRIDE } from "./scMapUtils";
import type { HighlightDefect } from "./types";
import type { DefectList } from "../../generated/proto/sc/v1/sample_pb";

type LegendSource = "class" | "bin" | "annotation" | "prediction" | "final_class";
type LegendKey = number | string;

const props = defineProps<{
  // Tab control
  activeMapTab?: "wafer" | "die" | "reticle";

  // Point data (all STRIDE=6 flat arrays)
  waferPoints?: number[];
  waferFullPoints?: number[];
  diePoints?: number[];
  dieFullPoints?: number[];
  reticlePoints?: number[];
  reticleFullPoints?: number[];

  // Wafer-specific
  waferGeometry?: {
    centerX: number;
    centerY: number;
    originX: number;
    originY: number;
    dieSizeX: number;
    dieSizeY: number;
  } | null;
  waferRadiusNm?: number;

  // Reticle-specific
  reticleXDieCount?: number;
  reticleYDieCount?: number;
  reticleDieSizeX?: number;
  reticleDieSizeY?: number;
  reticleOptions?: { xDieCount: number; yDieCount: number; xDieShift: number; yDieShift: number };

  // Loading / error
  mapLoading?: boolean;
  mapError?: string | null;
  mapProgressMessage?: string;
  mapProgressPercent?: number;

  // Legend control (optional)
  legendPoints?: number[];
  legendGroupBy?: LegendSource | null;
  legendSources?: LegendSource[];
  legendGroups?: Record<string, DefectList> | null;
  selectedIds?: ReadonlySet<number>;

  // Zoom viewport
  zoom?: { x: number; y: number; w: number; h: number } | null;

  /** Box-selection query function (mode, region) → defect IDs.
   *  Parent curries inspection identity; ScMapPanel curries mode for each child map. */
  queryBoxSelection?: (
    mode: "wafer" | "die" | "reticle",
    region: { x: number; y: number; w: number; h: number },
  ) => Promise<number[]>;

  // Highlight defects from table selection (purple overlay, self-contained coordinates)
  highlightDefects?: HighlightDefect[];
}>();

const emit = defineEmits<{
  (e: "update:activeMapTab", v: "wafer" | "die" | "reticle"): void;
  (
    e: "update:reticleOptions",
    v: { xDieCount: number; yDieCount: number; xDieShift: number; yDieShift: number },
  ): void;
  (
    e: "select-points",
    payload: {
      ids: number[];
      region: { x: number; y: number; w: number; h: number };
      key?: LegendKey | null;
    },
  ): void;
  (e: "zoom-in", vp: { x: number; y: number; w: number; h: number } | null): void;
  (e: "retry"): void;
  (e: "selection-change", ids: number[]): void;
  (e: "update:legendGroupBy", groupBy: LegendSource | null): void;
  (e: "legend-group-change", groupBy: string | null): void;
  (e: "legend-hidden-change", payload: { source: LegendSource; hiddenKeys: string[] }): void;
}>();

const internalTab = ref<"wafer" | "die" | "reticle">(props.activeMapTab ?? "wafer");
const mapMode = ref<Record<string, "select" | "zoomin">>({
  wafer: "select",
  die: "select",
  reticle: "select",
});
const initialLoadDone = ref(false);

watch(
  () => props.mapLoading,
  (loading) => {
    if (!loading) initialLoadDone.value = true;
  },
);

// Sync prop to internal state
watch(
  () => props.activeMapTab,
  (newVal) => {
    if (newVal && newVal !== internalTab.value) {
      internalTab.value = newVal;
    }
  },
);

const handleTabChange = (value: string | number) => {
  const tab = value as "wafer" | "die" | "reticle";
  emit("zoom-in", null);
  internalTab.value = tab;
  selectedClassNumber.value = null;
  emit("update:activeMapTab", tab);
};

const selectedClassNumber = ref<LegendKey | null>(null);
const selectedIds = ref<Set<number>>(new Set(props.selectedIds ?? []));
const legendSource = ref<LegendSource>(props.legendGroupBy ?? "class");
const hiddenLegendKeysBySource = ref<Record<LegendSource, string[]>>({
  class: [],
  bin: [],
  annotation: [],
  prediction: [],
  final_class: [],
});
const colorMap = ref<Record<string, string>>({});
const previousDefaultColorMap = ref<Record<string, string>>({});
const legendSourceOptions = computed(() => {
  const enabled = props.legendSources ?? ["class", "bin"];
  const labels: Record<LegendSource, string> = {
    class: "Class",
    bin: "Rough Bin",
    annotation: "Annotation",
    prediction: "Prediction (Latest)",
    final_class: "Final Class",
  };
  return enabled.map((value) => ({ value, label: labels[value] }));
});

watch(
  () => props.selectedIds,
  (ids) => {
    selectedIds.value = new Set(ids ?? []);
  },
  { deep: true },
);

watch(
  () => props.legendGroupBy,
  (newSource) => {
    const nextSource = newSource ?? "class";
    if (nextSource !== legendSource.value) {
      legendSource.value = nextSource;
    }
  },
);

const drawerVisible = ref<boolean>(!loadPersistedState("sc_map_panel.drawer_collapsed", false));
const mapAreaRef = ref<HTMLElement | null>(null);
const canvasTopPx = ref(36);
let tabsResizeObserver: ResizeObserver | null = null;

function updateCanvasTop(): void {
  const tabsNav = mapAreaRef.value?.querySelector<HTMLElement>(".n-tabs-nav");
  const height = tabsNav?.getBoundingClientRect().height ?? 0;
  if (height > 0) {
    canvasTopPx.value = Math.ceil(height);
  }
}

onMounted(() => {
  nextTick(() => {
    updateCanvasTop();
    const tabsNav = mapAreaRef.value?.querySelector<HTMLElement>(".n-tabs-nav");
    if (tabsNav && typeof ResizeObserver !== "undefined") {
      tabsResizeObserver = new ResizeObserver(updateCanvasTop);
      tabsResizeObserver.observe(tabsNav);
    }
  });
});

onBeforeUnmount(() => {
  tabsResizeObserver?.disconnect();
});

function loadPersistedState(key: string, defaultValue: boolean): boolean {
  const raw = localStorage.getItem(key);
  if (raw === null) return defaultValue;
  if (raw === "true") return true;
  if (raw === "false") return false;
  return defaultValue;
}

function savePersistedState(key: string, value: boolean): void {
  localStorage.setItem(key, String(value));
}

watch(legendSource, (newSource) => {
  emit("update:legendGroupBy", newSource);
  emit("legend-group-change", newSource || null);
  selectedClassNumber.value = null;
  selectedIds.value = new Set();
});

watch(drawerVisible, (val) => {
  savePersistedState("sc_map_panel.drawer_collapsed", !val);
});

// Curried queryBoxSelection for each map wrapper (bakes in the mode)
interface BoxRegion {
  x: number;
  y: number;
  w: number;
  h: number;
}
const waferBoxQuery = computed(() => {
  const q = props.queryBoxSelection;
  if (!q) return undefined;
  return async (region: BoxRegion) => filterVisibleIds(await q("wafer", region));
});
const dieBoxQuery = computed(() => {
  const q = props.queryBoxSelection;
  if (!q) return undefined;
  return async (region: BoxRegion) => filterVisibleIds(await q("die", region));
});
const reticleBoxQuery = computed(() => {
  const q = props.queryBoxSelection;
  if (!q) return undefined;
  return async (region: BoxRegion) => filterVisibleIds(await q("reticle", region));
});

const selectionIds = ref<number[]>([]);
const handleSelectionChange = (ids: number[]) => {
  selectedClassNumber.value = null;
  selectedIds.value = new Set(ids);
  selectionIds.value = ids;
  emit("selection-change", ids);
};

const handleZoomIn = (vp: { x: number; y: number; w: number; h: number } | null) => {
  emit("zoom-in", vp);
};

const handleRetry = () => {
  emit("retry");
};

const handleReticleOptionsSubmit = (opts: {
  xDieCount: number;
  yDieCount: number;
  xDieShift: number;
  yDieShift: number;
}) => {
  emit("update:reticleOptions", opts);
};

// Use explicit legendPoints if provided, otherwise fallback to the active tab's fullPoints
const currentLegendPoints = computed(() => {
  if (props.legendPoints) {
    return props.legendPoints;
  }
  if (internalTab.value === "wafer") {
    return props.waferFullPoints ?? props.waferPoints ?? [];
  }
  if (internalTab.value === "die") {
    return props.dieFullPoints ?? props.diePoints ?? [];
  }
  if (internalTab.value === "reticle") {
    return props.reticleFullPoints ?? props.reticlePoints ?? [];
  }
  return [];
});

const parsedCache = computed(() => parsePoints(currentLegendPoints.value));
const activeHiddenLegendKeys = computed(
  () => hiddenLegendKeysBySource.value[legendSource.value] ?? [],
);
const activeHiddenLegendKeySet = computed(() => new Set(activeHiddenLegendKeys.value));

function hiddenDefectIdsForSource(source: LegendSource, hiddenKeys: Set<string>): Set<number> {
  const hiddenIds = new Set<number>();
  if (hiddenKeys.size === 0) return hiddenIds;

  const compactGroups = props.legendGroups ?? undefined;
  if (compactGroups && (source === "annotation" || source === "prediction")) {
    for (const key of hiddenKeys) {
      for (const defectId of compactGroups[key]?.defectIds ?? []) {
        hiddenIds.add(Number(defectId));
      }
    }
    return hiddenIds;
  }

  for (const point of parsePoints(currentLegendPoints.value)) {
    const key = source === "bin" ? String(point.roughBin) : String(point.classNumber);
    if (hiddenKeys.has(key)) hiddenIds.add(point.defectId);
  }
  return hiddenIds;
}

const hiddenDefectIds = computed(() =>
  hiddenDefectIdsForSource(legendSource.value, activeHiddenLegendKeySet.value),
);

function filterPointArray(points?: number[]): number[] | undefined {
  if (!points) return points;
  const hidden = hiddenDefectIds.value;
  if (hidden.size === 0) return points;
  const result: number[] = [];
  for (let i = 0; i + STRIDE - 1 < points.length; i += STRIDE) {
    const defectId = points[i + 2];
    if (!hidden.has(defectId)) {
      result.push(...points.slice(i, i + STRIDE));
    }
  }
  return result;
}

const visibleWaferPoints = computed(() => filterPointArray(props.waferPoints));
const visibleDiePoints = computed(() => filterPointArray(props.diePoints));
const visibleReticlePoints = computed(() => filterPointArray(props.reticlePoints));

function filterVisibleIds(ids: number[]): number[] {
  const hidden = hiddenDefectIds.value;
  if (hidden.size === 0) return ids;
  return ids.filter((id) => !hidden.has(id));
}

function sortLegendKeys(keys: string[]): string[] {
  return [...keys].sort((a, b) => String(a).localeCompare(String(b), undefined, { numeric: true }));
}

function colorMapKeyForLegendKey(
  source: LegendSource,
  rawKey: string,
  compactGroups?: Record<string, DefectList>,
): string {
  if (source === "class" || source === "bin" || !compactGroups) {
    return rawKey;
  }
  if (rawKey === "__unlabeled__" || rawKey === "__no_prediction__") {
    return "-1";
  }
  return String(
    sortLegendKeys(
      Object.keys(compactGroups).filter(
        (key) => key !== "__unlabeled__" && key !== "__no_prediction__",
      ),
    ).indexOf(rawKey),
  );
}

const defaultColorMap = computed<Record<string, string>>(() => {
  const source = legendSource.value;
  const compactGroups = props.legendGroups ?? undefined;
  const map: Record<string, string> = {};
  if (compactGroups && Object.keys(compactGroups).length > 0) {
    for (const rawKey of Object.keys(compactGroups)) {
      map[colorMapKeyForLegendKey(source, rawKey, compactGroups)] = legendColor(source, rawKey);
    }
    return map;
  }

  const points = currentLegendPoints.value;
  for (let i = 0; i + STRIDE - 1 < points.length; i += STRIDE) {
    const key = String(points[i + 3]);
    map[key] = legendColor(source, key);
  }
  return map;
});

watch(
  defaultColorMap,
  (defaults) => {
    const previous = previousDefaultColorMap.value;
    const next: Record<string, string> = {};
    for (const [key, defaultColor] of Object.entries(defaults)) {
      const currentColor = colorMap.value[key];
      next[key] = currentColor && currentColor !== previous[key] ? currentColor : defaultColor;
    }
    colorMap.value = next;
    previousDefaultColorMap.value = { ...defaults };
  },
  { immediate: true },
);

const annotationGroups = computed(() =>
  legendSource.value === "annotation" ? (props.legendGroups ?? undefined) : undefined,
);
const predictionGroups = computed(() =>
  legendSource.value === "prediction" ? (props.legendGroups ?? undefined) : undefined,
);
const finalClassGroups = computed(() =>
  legendSource.value === "final_class" ? (props.legendGroups ?? undefined) : undefined,
);

const showMapProgress = computed(
  () => Boolean(props.mapLoading) && Boolean(props.mapProgressMessage) && !initialLoadDone.value,
);

const ZERO_REGION = { x: 0, y: 0, w: 0, h: 0 };

const handleLegendSelect = (key: LegendKey | null) => {
  if (key === null) {
    selectedClassNumber.value = null;
    selectedIds.value = new Set();
    emit("select-points", { ids: [], region: ZERO_REGION, key });
  } else {
    selectedClassNumber.value = key;
    const compactGroup = props.legendGroups?.[String(key)];
    const ids =
      compactGroup?.defectIds ??
      (typeof key === "number"
        ? parsedCache.value
            .filter((point) => point.classNumber === key)
            .map((point) => point.defectId)
        : []);
    const visibleIds = filterVisibleIds(ids);
    selectedIds.value = new Set(visibleIds);
    emit("select-points", { ids: visibleIds, region: ZERO_REGION, key });
  }
};

function handleHiddenLegendKeysUpdate(keys: string[]): void {
  const source = legendSource.value;
  hiddenLegendKeysBySource.value = {
    ...hiddenLegendKeysBySource.value,
    [source]: keys,
  };
  const nextSelection = filterVisibleIds(Array.from(selectedIds.value));
  selectedIds.value = new Set(nextSelection);
  selectionIds.value = filterVisibleIds(selectionIds.value);
  emit("selection-change", selectionIds.value);
  emit("legend-hidden-change", { source, hiddenKeys: keys });
}
</script>

<template>
  <div class="sc-map-panel" data-testid="sc-map-panel">
    <div v-if="mapError" class="sc-map-error">
      <NResult status="error" title="Map Error" :description="mapError">
        <template #footer>
          <NButton @click="handleRetry">Retry</NButton>
        </template>
      </NResult>
    </div>

    <div v-else class="sc-map-content">
      <div
        class="sc-map-body"
        data-testid="sc-map-toolbar-container"
        :style="{ '--sc-map-canvas-top': `${canvasTopPx}px` }"
      >
        <div ref="mapAreaRef" class="map-area">
          <div v-if="showMapProgress" class="sc-map-progress">
            <NProgress
              type="line"
              :percentage="mapProgressPercent ?? 0"
              :indicator-placement="'inside'"
              processing
            />
            <NText depth="3" class="sc-map-progress-text">
              {{ mapProgressMessage }}
            </NText>
          </div>
          <div class="map-tabs-row">
            <NTabs
              :value="internalTab"
              @update:value="handleTabChange"
              type="line"
              size="small"
              display-directive="show"
              style="flex: 1; min-height: 0; display: flex; flex-direction: column"
            >
              <NTabPane name="wafer" tab="Wafer" data-testid="sc-map-tab-wafer">
                <ScWaferMap
                  :points="visibleWaferPoints"
                  :geometry="waferGeometry"
                  :waferRadiusNm="waferRadiusNm"
                  :selectedIds="selectedIds"
                  :highlightDefects="highlightDefects"
                  :color-map="colorMap"
                  :query-box-selection="waferBoxQuery"
                  :zoom="zoom"
                  :mode="mapMode.wafer"
                  @selection-change="handleSelectionChange"
                  @zoom-in="handleZoomIn"
                />
              </NTabPane>

              <NTabPane name="die" tab="Die Stack" data-testid="sc-map-tab-die">
                <ScDieStackMap
                  :points="visibleDiePoints"
                  :die-size-x="waferGeometry?.dieSizeX"
                  :die-size-y="waferGeometry?.dieSizeY"
                  :selectedIds="selectedIds"
                  :highlightDefects="highlightDefects"
                  :color-map="colorMap"
                  :query-box-selection="dieBoxQuery"
                  :zoom="zoom"
                  :mode="mapMode.die"
                  @selection-change="handleSelectionChange"
                  @zoom-in="handleZoomIn"
                />
              </NTabPane>

              <NTabPane name="reticle" tab="Reticle" data-testid="sc-map-tab-reticle">
                <ScReticleMap
                  v-if="
                    reticleXDieCount !== undefined &&
                    reticleYDieCount !== undefined &&
                    reticleDieSizeX !== undefined &&
                    reticleDieSizeY !== undefined
                  "
                  :points="visibleReticlePoints"
                  :xDieCount="reticleXDieCount"
                  :yDieCount="reticleYDieCount"
                  :dieSizeX="reticleDieSizeX"
                  :dieSizeY="reticleDieSizeY"
                  :selectedIds="selectedIds"
                  :highlightDefects="highlightDefects"
                  :color-map="colorMap"
                  :query-box-selection="reticleBoxQuery"
                  :zoom="zoom"
                  :mode="mapMode.reticle"
                  @selection-change="handleSelectionChange"
                  @zoom-in="handleZoomIn"
                />
                <div v-else class="reticle-map-placeholder">Missing reticle configuration</div>
              </NTabPane>
            </NTabs>
          </div>
          <div class="map-toolbar">
            <div class="map-toolbar-actions">
              <NTooltip placement="bottom">
                <template #trigger>
                  <NButton
                    data-testid="sc-map-select-tool"
                    size="small"
                    quaternary
                    :type="mapMode[internalTab] === 'select' ? 'primary' : 'default'"
                    aria-label="Box selection"
                    @click="mapMode[internalTab] = 'select'"
                  >
                    <template #icon
                      ><NIcon><ScanOutline /></NIcon
                    ></template>
                  </NButton>
                </template>
                Box selection
              </NTooltip>
              <NTooltip placement="bottom">
                <template #trigger>
                  <NButton
                    data-testid="sc-map-zoom-tool"
                    size="small"
                    quaternary
                    :type="mapMode[internalTab] === 'zoomin' ? 'primary' : 'default'"
                    aria-label="Zoom in"
                    @click="mapMode[internalTab] = 'zoomin'"
                  >
                    <template #icon>
                      <span class="zoom-in-icon">
                        <NIcon><SearchOutline /></NIcon>
                        <NIcon class="zoom-in-icon__plus"><AddOutline /></NIcon>
                      </span>
                    </template>
                  </NButton>
                </template>
                Zoom in
              </NTooltip>
              <ScReticleMapOptionsButton
                v-if="internalTab === 'reticle' && reticleOptions"
                :modelValue="reticleOptions"
                size="small"
                icon-only
                quaternary
                @submit="handleReticleOptionsSubmit"
              />
            </div>
          </div>
        </div>

        <aside
          data-testid="sc-map-drawer"
          class="legend-drawer"
          :class="{ 'legend-drawer--collapsed': !drawerVisible }"
          :style="{
            width: drawerVisible ? '190px' : '0px',
            minWidth: drawerVisible ? '190px' : '0px',
          }"
        >
          <NButton
            data-testid="sc-map-drawer-toggle"
            class="drawer-toggle"
            size="tiny"
            quaternary
            @click="drawerVisible = !drawerVisible"
          >
            <template #icon>
              <NIcon>
                <ArrowForwardOutline v-if="drawerVisible" />
                <ArrowBackOutline v-else />
              </NIcon>
            </template>
          </NButton>

          <NTabs
            v-show="drawerVisible"
            type="segment"
            animated
            data-testid="sc-map-drawer-tabs"
            size="small"
            style="flex: 1; min-height: 0; display: flex; flex-direction: column"
          >
            <NTabPane
              name="legend"
              tab="Legend"
              data-testid="sc-legend-tab"
              style="flex: 1; min-height: 0; display: flex; flex-direction: column"
            >
              <div class="drawer-header">
                <NSelect
                  data-testid="sc-legend-source-select"
                  v-model:value="legendSource"
                  :options="legendSourceOptions"
                  size="small"
                  placeholder="Source"
                />
              </div>

              <div style="flex: 1; min-height: 0; overflow-y: auto">
                <ScLegend
                  :points="[]"
                  :fullPoints="currentLegendPoints"
                  :class-numbers="
                    legendSource === 'class' ? (legendGroups ?? undefined) : undefined
                  "
                  :rough-bins="legendSource === 'bin' ? (legendGroups ?? undefined) : undefined"
                  :annotations="annotationGroups"
                  :predictions="predictionGroups"
                  :final-class="finalClassGroups"
                  :color-map="colorMap"
                  :selectedClassNumber="selectedClassNumber"
                  :legendSource="legendSource"
                  :hidden-keys="activeHiddenLegendKeys"
                  @select-class="handleLegendSelect"
                  @update:color-map="colorMap = $event"
                  @update:hidden-keys="handleHiddenLegendKeysUpdate"
                />
              </div>
            </NTabPane>
          </NTabs>
        </aside>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sc-map-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  min-width: 0;
}

.sc-map-content {
  display: flex;
  flex-direction: column;
  flex-grow: 1;
  min-height: 0;
  min-width: 0;
}

.sc-map-body {
  display: flex;
  flex-direction: row;
  flex-grow: 1;
  min-height: 0;
}

.map-area {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
}

.map-tabs-row {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  flex: 1;
  min-height: 0;
}

.sc-map-progress {
  position: absolute;
  left: 50%;
  top: calc(var(--sc-map-canvas-top) + (100% - var(--sc-map-canvas-top)) / 2);
  width: min(320px, calc(100% - 48px));
  transform: translate(-50%, -50%);
  z-index: 100;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid var(--n-border-color);
  border-radius: 6px;
  background: var(--n-color);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
  pointer-events: none;
}

.sc-map-progress-text {
  font-size: 12px;
  text-align: center;
}

.map-area :deep(.n-tabs) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-self: stretch;
}

.map-area :deep(.n-tab-pane) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.map-area :deep(.n-spin-container) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.map-area :deep(.n-spin-content) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.legend-drawer {
  position: relative;
  flex-shrink: 0;
  margin-left: 6px;
  margin-top: var(--sc-map-canvas-top);
  height: calc(100% - var(--sc-map-canvas-top));
  overflow: hidden;
  min-height: 0;
  transition: width 0.2s ease;
  display: flex;
  flex-direction: column;
}

.drawer-toggle {
  position: absolute;
  left: -24px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 10;
  width: 24px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.drawer-header {
  padding: 8px 8px 4px;
  flex-shrink: 0;
}

/* Ensure drawer NTabs legend/filter panes scroll properly */
.legend-drawer :deep(.n-tabs-pane-wrapper) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.legend-drawer :deep(.n-tab-pane) {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
}

.sc-map-error {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-grow: 1;
}

.reticle-map-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 300px;
  background-color: var(--n-color-embedded);
  color: var(--n-text-color-3);
  border-radius: var(--n-border-radius);
}

.map-toolbar {
  position: absolute;
  top: 2px;
  right: 8px;
  z-index: 10;
  display: flex;
  flex-direction: row;
  align-items: center;
  min-height: calc(var(--sc-map-canvas-top) - 2px);
  pointer-events: none;
}

.map-toolbar-actions {
  display: flex;
  flex-direction: row;
  gap: 4px;
  pointer-events: auto;
}

.zoom-in-icon {
  position: relative;
  display: inline-flex;
  width: 1em;
  height: 1em;
}

.zoom-in-icon__plus {
  position: absolute;
  top: -3px;
  right: -5px;
  padding: 1px;
  font-size: 9px;
  border-radius: 50%;
  background: var(--n-color, #fff);
}
</style>
