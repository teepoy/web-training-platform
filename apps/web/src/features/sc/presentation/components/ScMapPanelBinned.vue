<script setup lang="ts">
import { computed, onUnmounted, onUpdated, ref, watch } from "vue";
import {
  NTabs,
  NTabPane,
  NResult,
  NButton,
  NSelect,
  NIcon,
  NTooltip,
  NSpin,
  NText,
} from "naive-ui";
import { ArrowBackOutline, ArrowForwardOutline } from "@vicons/ionicons5";
import { AddOutline, ScanOutline, SearchOutline } from "@vicons/ionicons5";
import ScWaferMap from "./ScWaferMapPerspective.vue";
import ScDieStackMap from "./ScDieStackMapPerspective.vue";
import ScReticleMap from "./ScReticleMapPerspective.vue";
import ScLegend from "./ScLegend.vue";
import ScReticleMapOptionsButton from "./ScReticleMapOptionsButton.vue";
import { legendColor } from "./scMapUtils";
import type { DefectList } from "../../generated/proto/sc/v1/sample_pb";
import type { HighlightDefect } from "./types";
import type { MapDisplayArray } from "./transforms/binsToDisplayArrays";

type LegendSource = "class" | "bin" | "annotation" | "prediction" | "final_class";
type LegendKey = number | string;
type BoxSelectionRegion = { x: number; y: number; w: number; h: number };
type CrosshairPoint = { x: number; y: number };
type MapTab = "wafer" | "die" | "reticle";
type QueuedBoxSelection = { tab: MapTab; region: BoxSelectionRegion };

const BOX_SELECTION_DEBOUNCE_MS = 1000;

const props = defineProps<{
  activeMapTab?: "wafer" | "die" | "reticle";

  waferPoints?: MapDisplayArray | number[];
  diePoints?: MapDisplayArray | number[];
  reticlePoints?: MapDisplayArray | number[];

  waferGeometry?: {
    centerX: number;
    centerY: number;
    originX: number;
    originY: number;
    dieSizeX: number;
    dieSizeY: number;
  } | null;
  waferRadiusNm?: number;

  reticleXDieCount?: number;
  reticleYDieCount?: number;
  reticleDieSizeX?: number;
  reticleDieSizeY?: number;
  reticleOptions?: { xDieCount: number; yDieCount: number; xDieShift: number; yDieShift: number };

  mapLoading?: boolean;
  mapError?: string | null;
  mapProgressMessage?: string;
  mapProgressPercent?: number;

  legendGroupBy?: LegendSource | null;
  legendSources?: LegendSource[];
  legendGroups?: Record<string, DefectList> | null;

  zoom?: { x: number; y: number; w: number; h: number } | null;

  /** Highlight defects from gallery selection (purple dots on overlay canvas). */
  highlightDefects?: HighlightDefect[];
  immediateCrosshairDefects?: HighlightDefect[];
  immediateCrosshairVersion?: number;
}>();

const emit = defineEmits<{
  (e: "update:activeMapTab", v: "wafer" | "die" | "reticle"): void;
  (
    e: "update:reticleOptions",
    v: { xDieCount: number; yDieCount: number; xDieShift: number; yDieShift: number },
  ): void;
  (
    e: "legend-select",
    payload: {
      ids: number[];
      region: { x: number; y: number; w: number; h: number };
      key?: LegendKey | null;
    },
  ): void;
  (e: "zoom-in", vp: { x: number; y: number; w: number; h: number } | null): void;
  (e: "retry"): void;
  (e: "selection-change", ids: number[]): void;
  (e: "legend-group-change", groupBy: string | null): void;
  (e: "legend-hidden-change", payload: { source: LegendSource; hiddenKeys: string[] }): void;
  (e: "box-select", region: { x: number; y: number; w: number; h: number }): void;
}>();

const internalTab = ref<MapTab>(props.activeMapTab ?? "wafer");
const mapMode = ref<Record<string, "select" | "zoomin">>({
  wafer: "select",
  die: "select",
  reticle: "select",
});
const drawerVisible = ref<boolean>(!loadPersistedState("sc_map_panel.drawer_collapsed", false));

watch(
  () => props.activeMapTab,
  (newVal) => {
    if (newVal && newVal !== internalTab.value) {
      internalTab.value = newVal;
    }
  },
);

const handleTabChange = (value: string | number) => {
  const tab = value as MapTab;
  clearQueuedBoxSelection();
  clearLocalImmediateCrosshair();
  emit("zoom-in", null);
  internalTab.value = tab;
  selectedClassNumber.value = null;
  emit("update:activeMapTab", tab);
};

const selectedClassNumber = ref<LegendKey | null>(null);
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
  () => props.legendGroupBy,
  (newSource) => {
    const nextSource = newSource ?? "class";
    if (nextSource !== legendSource.value) {
      legendSource.value = nextSource;
    }
  },
);

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
  emit("legend-group-change", newSource || null);
  selectedClassNumber.value = null;
});

watch(drawerVisible, (val) => {
  savePersistedState("sc_map_panel.drawer_collapsed", !val);
});

const handleSelectionChange = (ids: number[]) => {
  selectedClassNumber.value = null;
  if (ids.length === 0) clearQueuedBoxSelection();
  emit("selection-change", ids);
};

const handleZoomIn = (vp: { x: number; y: number; w: number; h: number } | null) => {
  clearLocalImmediateCrosshair();
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

const activeHiddenLegendKeys = computed(
  () => hiddenLegendKeysBySource.value[legendSource.value] ?? [],
);

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
  }
  return map;
});

watch(
  defaultColorMap,
  (defaults) => {
    console.debug("[panel] ScMapPanelBinned defaultColorMap watcher → colorMap rebuild");
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
const localImmediateCrosshairPoints = ref<Record<MapTab, CrosshairPoint[]>>({
  wafer: [],
  die: [],
  reticle: [],
});
const localImmediateCrosshairVersion = ref(0);
const resolvedImmediateCrosshairVersion = computed(
  () => (props.immediateCrosshairVersion ?? 0) + localImmediateCrosshairVersion.value * 1_000_000,
);

function clearLocalImmediateCrosshair(): void {
  localImmediateCrosshairPoints.value = { wafer: [], die: [], reticle: [] };
  localImmediateCrosshairVersion.value += 1;
}

function handleImmediateCrosshairPoints(points: CrosshairPoint[]): void {
  if (points.length === 0) {
    localImmediateCrosshairPoints.value = {
      ...localImmediateCrosshairPoints.value,
      [internalTab.value]: [],
    };
  } else {
    localImmediateCrosshairPoints.value = {
      ...localImmediateCrosshairPoints.value,
      [internalTab.value]: [...localImmediateCrosshairPoints.value[internalTab.value], ...points],
    };
  }
  localImmediateCrosshairVersion.value += 1;
}

watch(
  () => props.immediateCrosshairVersion,
  () => {
    localImmediateCrosshairPoints.value = { wafer: [], die: [], reticle: [] };
  },
);

const waferImmediateCrosshairPoints = computed<CrosshairPoint[]>(() => [
  ...(props.immediateCrosshairDefects ?? []).map((defect) => ({
    x: defect.waferX,
    y: defect.waferY,
  })),
  ...localImmediateCrosshairPoints.value.wafer,
]);
const dieImmediateCrosshairPoints = computed<CrosshairPoint[]>(() => [
  ...(props.immediateCrosshairDefects ?? []).map((defect) => ({ x: defect.dieX, y: defect.dieY })),
  ...localImmediateCrosshairPoints.value.die,
]);
const reticleImmediateCrosshairPoints = computed<CrosshairPoint[]>(() => [
  ...(props.immediateCrosshairDefects ?? []).map((defect) => ({
    x: defect.reticleX,
    y: defect.reticleY,
  })),
  ...localImmediateCrosshairPoints.value.reticle,
]);

let queuedBoxSelections: QueuedBoxSelection[] = [];
let boxSelectionTimer: number | null = null;

function clearQueuedBoxSelection(): void {
  queuedBoxSelections = [];
  if (boxSelectionTimer !== null) {
    clearTimeout(boxSelectionTimer);
    boxSelectionTimer = null;
  }
}

function flushQueuedBoxSelection(): void {
  boxSelectionTimer = null;
  const selections = queuedBoxSelections;
  queuedBoxSelections = [];
  for (const selection of selections) {
    if (selection.tab === internalTab.value) emit("box-select", selection.region);
  }
}

function onBoxSelect(region: BoxSelectionRegion): void {
  queuedBoxSelections.push({ tab: internalTab.value, region });
  if (boxSelectionTimer === null) {
    boxSelectionTimer = window.setTimeout(flushQueuedBoxSelection, BOX_SELECTION_DEBOUNCE_MS);
  }
}

const handleLegendSelect = (key: LegendKey | null) => {
  if (key === null) {
    selectedClassNumber.value = null;
    emit("legend-select", { ids: [], region: { x: 0, y: 0, w: 0, h: 0 }, key });
  } else {
    selectedClassNumber.value = key;
    emit("legend-select", { ids: [], region: { x: 0, y: 0, w: 0, h: 0 }, key });
  }
};

function handleHiddenLegendKeysUpdate(keys: string[]): void {
  const source = legendSource.value;
  hiddenLegendKeysBySource.value = {
    ...hiddenLegendKeysBySource.value,
    [source]: keys,
  };
  emit("legend-hidden-change", { source, hiddenKeys: keys });
}

onUpdated(() => console.debug("[render] ScMapPanelBinned"));

onUnmounted(() => {
  clearQueuedBoxSelection();
});
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
      <div class="sc-map-tabs-bar">
        <NTabs
          :value="internalTab"
          @update:value="handleTabChange"
          type="line"
          size="small"
          style="flex: 1"
        >
          <NTabPane name="wafer" tab="Wafer" data-testid="sc-map-tab-wafer" />
          <NTabPane name="die" tab="Die Stack" data-testid="sc-map-tab-die" />
          <NTabPane name="reticle" tab="Reticle" data-testid="sc-map-tab-reticle" />
        </NTabs>
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

      <div class="sc-map-body" data-testid="sc-map-toolbar-container">
        <div class="map-area">
          <div v-if="mapLoading" class="map-loading-overlay">
            <NSpin size="small" />
            <NText depth="3" class="map-loading-text">
              {{ mapProgressMessage ?? "Loading map..." }}
            </NText>
          </div>
          <ScWaferMap
            v-if="internalTab === 'wafer'"
            :points="waferPoints"
            :geometry="waferGeometry"
            :waferRadiusNm="waferRadiusNm"
            :color-map="colorMap"
            :zoom="zoom"
            :mode="mapMode.wafer"
            :highlightDefects="highlightDefects"
            :immediate-crosshair-points="waferImmediateCrosshairPoints"
            :immediate-crosshair-version="resolvedImmediateCrosshairVersion"
            @immediate-crosshair-points="handleImmediateCrosshairPoints"
            @selection-change="handleSelectionChange"
            @zoom-in="handleZoomIn"
            @box-select="onBoxSelect"
          />
          <ScDieStackMap
            v-else-if="internalTab === 'die'"
            :points="diePoints"
            :die-size-x="waferGeometry?.dieSizeX"
            :die-size-y="waferGeometry?.dieSizeY"
            :color-map="colorMap"
            :zoom="zoom"
            :mode="mapMode.die"
            :highlightDefects="highlightDefects"
            :immediate-crosshair-points="dieImmediateCrosshairPoints"
            :immediate-crosshair-version="resolvedImmediateCrosshairVersion"
            @immediate-crosshair-points="handleImmediateCrosshairPoints"
            @selection-change="handleSelectionChange"
            @zoom-in="handleZoomIn"
            @box-select="onBoxSelect"
          />
          <ScReticleMap
            v-else-if="internalTab === 'reticle'"
            :points="reticlePoints"
            :x-die-count="reticleXDieCount"
            :y-die-count="reticleYDieCount"
            :die-size-x="reticleDieSizeX"
            :die-size-y="reticleDieSizeY"
            :color-map="colorMap"
            :zoom="zoom"
            :mode="mapMode.reticle"
            :highlightDefects="highlightDefects"
            :immediate-crosshair-points="reticleImmediateCrosshairPoints"
            :immediate-crosshair-version="resolvedImmediateCrosshairVersion"
            @immediate-crosshair-points="handleImmediateCrosshairPoints"
            @selection-change="handleSelectionChange"
            @zoom-in="handleZoomIn"
            @box-select="onBoxSelect"
          />
          <div v-else-if="internalTab === 'reticle'" class="reticle-map-placeholder">
            Missing reticle configuration
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
                  :fullPoints="[]"
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

.sc-map-tabs-bar {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 4px;
  flex: none;
  border-bottom: 1px solid var(--n-border-color);
}

.sc-map-tabs-bar .map-toolbar-actions {
  display: flex;
  flex-direction: row;
  gap: 4px;
  padding-right: 4px;
  flex: none;
}

.sc-map-body {
  display: flex;
  flex-direction: row;
  flex-grow: 1;
  min-height: 0;
}

.map-area {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 0;
}

.map-loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 5;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: color-mix(in srgb, var(--n-color), transparent 18%);
}

.map-loading-text {
  font-size: 12px;
}

.legend-drawer {
  position: relative;
  flex-shrink: 0;
  margin-left: 6px;
  height: 100%;
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
