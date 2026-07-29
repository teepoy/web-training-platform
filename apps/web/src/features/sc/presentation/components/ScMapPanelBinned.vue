<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { defineScMapElement, type ScMapGeometry } from "@platform/sc-map-element";
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
import {
  AddOutline,
  MoveOutline,
  RemoveOutline,
  ScanOutline,
  SearchOutline,
} from "@vicons/ionicons5";
import ScLegend from "./ScLegend.vue";
import ScReticleMapOptionsButton from "./ScReticleMapOptionsButton.vue";
import { legendColor } from "./scMapUtils";
import type { DefectList } from "../../generated/proto/sc/v1/sample_pb";
import type { HighlightDefect } from "./types";

if (import.meta.env.MODE !== "test") defineScMapElement();

type LegendSource = "class" | "bin" | "annotation" | "prediction" | "final_class";
type LegendKey = number | string;
type BoxSelectionRegion = { x: number; y: number; w: number; h: number };
type CrosshairPoint = { x: number; y: number };
type MapTab = "wafer" | "die" | "reticle";

const props = withDefaults(
  defineProps<{
    activeMapTab?: "wafer" | "die" | "reticle";
    arrowData?: ArrayBuffer | readonly ArrayBuffer[] | null;
    mapLegendColumn?: string;

    waferGeometry?: {
      centerX: number;
      centerY: number;
      originX: number;
      originY: number;
      dieSizeX: number;
      dieSizeY: number;
    } | null;
    waferRadiusNm?: number;

    reticleDieSizeX?: number;
    reticleDieSizeY?: number;
    reticleOptions?: { xDieCount: number; yDieCount: number; xDieShift: number; yDieShift: number };
    showImageMarkers?: boolean;
    defectSize?: number;

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
  }>(),
  {
    showImageMarkers: true,
    defectSize: 2,
  },
);

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
  (e: "update:showImageMarkers", value: boolean): void;
  (e: "update:defectSize", value: number): void;
}>();

const internalTab = ref<MapTab>(props.activeMapTab ?? "wafer");
const mapMode = ref<Record<string, "select" | "zoomin" | "pan">>({
  wafer: "select",
  die: "select",
  reticle: "select",
});
const drawerVisible = ref<boolean>(!loadPersistedState("sc_map_panel.drawer_collapsed", false));
const nativeMapLoading = ref(false);
const nativeMapError = ref<string | null>(null);
const nativeMapProgressMessage = ref("");
const keepMapVisibleWhileRendering = ref(false);
const showImageMarkers = ref(props.showImageMarkers ?? true);
const defectSize = ref(props.defectSize ?? 2);
const effectiveReticleOptions = computed(() => ({
  xDieCount: props.reticleOptions?.xDieCount ?? 2,
  yDieCount: props.reticleOptions?.yDieCount ?? 6,
  xDieShift: props.reticleOptions?.xDieShift ?? 0,
  yDieShift: props.reticleOptions?.yDieShift ?? 0,
}));

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

const handleZoomIn = (vp: { x: number; y: number; w: number; h: number } | null) => {
  clearLocalImmediateCrosshair();
  emit("zoom-in", vp);
};

function fullMapRegion(): { x: number; y: number; w: number; h: number } {
  const geometry = nativeGeometry.value;
  if (internalTab.value === "wafer") {
    return {
      x: geometry.centerX - geometry.waferRadiusNm,
      y: geometry.centerY - geometry.waferRadiusNm,
      w: geometry.waferRadiusNm * 2,
      h: geometry.waferRadiusNm * 2,
    };
  }
  if (internalTab.value === "die") {
    return { x: 0, y: 0, w: geometry.dieSizeX, h: geometry.dieSizeY };
  }
  return {
    x: 0,
    y: 0,
    w: geometry.dieSizeX * geometry.reticleXDieCount,
    h: geometry.dieSizeY * geometry.reticleYDieCount,
  };
}

function zoomBy(factor: number): void {
  clearLocalImmediateCrosshair();
  const full = fullMapRegion();
  const current = props.zoom ?? full;
  const width = Math.min(full.w, current.w * factor);
  const height = Math.min(full.h, current.h * factor);
  if (factor > 1 && width >= full.w && height >= full.h) {
    emit("zoom-in", null);
    return;
  }
  const centerX = current.x + current.w / 2;
  const centerY = current.y + current.h / 2;
  emit("zoom-in", {
    x: Math.min(full.x + full.w - width, Math.max(full.x, centerX - width / 2)),
    y: Math.min(full.y + full.h - height, Math.max(full.y, centerY - height / 2)),
    w: width,
    h: height,
  });
}

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

function handleMapDisplaySubmit(options: { showImageMarkers: boolean; defectSize: number }): void {
  showImageMarkers.value = options.showImageMarkers;
  defectSize.value = options.defectSize;
  emit("update:showImageMarkers", options.showImageMarkers);
  emit("update:defectSize", options.defectSize);
}

watch(
  () => props.showImageMarkers,
  (value) => {
    if (value !== undefined) showImageMarkers.value = value;
  },
);
watch(
  () => props.defectSize,
  (value) => {
    if (value !== undefined) defectSize.value = value;
  },
);

const activeHiddenLegendKeys = computed(
  () => hiddenLegendKeysBySource.value[legendSource.value] ?? [],
);

const defaultColorMap = computed<Record<string, string>>(() => {
  const source = legendSource.value;
  const compactGroups = props.legendGroups ?? undefined;
  const map: Record<string, string> = {};
  if (compactGroups && Object.keys(compactGroups).length > 0) {
    for (const rawKey of Object.keys(compactGroups)) {
      map[rawKey] = legendColor(source, rawKey);
    }
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
const localImmediateCrosshairPoints = ref<Record<MapTab, CrosshairPoint[]>>({
  wafer: [],
  die: [],
  reticle: [],
});
const nativeGeometry = computed<ScMapGeometry>(() => ({
  waferRadiusNm: props.waferRadiusNm ?? 150_000_000,
  centerX: props.waferGeometry?.centerX ?? 0,
  centerY: props.waferGeometry?.centerY ?? 0,
  originX: props.waferGeometry?.originX ?? 0,
  originY: props.waferGeometry?.originY ?? 0,
  dieSizeX: props.waferGeometry?.dieSizeX ?? props.reticleDieSizeX ?? 100_000,
  dieSizeY: props.waferGeometry?.dieSizeY ?? props.reticleDieSizeY ?? 100_000,
  reticleXDieCount: effectiveReticleOptions.value.xDieCount,
  reticleYDieCount: effectiveReticleOptions.value.yDieCount,
}));

const activeImmediatePoints = computed(() => {
  if (internalTab.value === "die") return dieImmediateCrosshairPoints.value;
  if (internalTab.value === "reticle") return reticleImmediateCrosshairPoints.value;
  return waferImmediateCrosshairPoints.value;
});

function onNativeZoom(event: Event): void {
  keepMapVisibleWhileRendering.value = mapMode.value[internalTab.value] === "pan";
  handleZoomIn(
    (event as CustomEvent<{ x: number; y: number; w: number; h: number } | null>).detail,
  );
}

function onNativeBoxSelect(event: Event): void {
  onBoxSelect((event as CustomEvent<BoxSelectionRegion>).detail);
}

function onNativeImmediateCrosshair(event: Event): void {
  localImmediateCrosshairPoints.value = {
    ...localImmediateCrosshairPoints.value,
    [internalTab.value]: (event as CustomEvent<CrosshairPoint[]>).detail,
  };
}

function onNativeMapProgress(event: Event): void {
  const detail = (event as CustomEvent<{ progress: number; stage: string }>).detail;
  nativeMapLoading.value = detail.progress < 1;
  nativeMapProgressMessage.value = detail.stage;
  nativeMapError.value = null;
}

function onNativeMapReady(): void {
  nativeMapLoading.value = false;
  keepMapVisibleWhileRendering.value = false;
  nativeMapProgressMessage.value = "Map ready";
}

function onNativeMapError(event: Event): void {
  nativeMapLoading.value = false;
  keepMapVisibleWhileRendering.value = false;
  nativeMapError.value = String((event as CustomEvent<unknown>).detail);
}

watch(
  () => props.arrowData,
  (arrow) => {
    nativeMapLoading.value = arrow !== null && arrow !== undefined;
    nativeMapError.value = null;
  },
);

const effectiveMapLoading = computed(
  () =>
    !keepMapVisibleWhileRendering.value && (Boolean(props.mapLoading) || nativeMapLoading.value),
);
const effectiveMapError = computed(() => props.mapError ?? nativeMapError.value);
const effectiveMapProgressMessage = computed(
  () =>
    (nativeMapLoading.value ? nativeMapProgressMessage.value : props.mapProgressMessage) ||
    "Loading map...",
);

function clearLocalImmediateCrosshair(): void {
  localImmediateCrosshairPoints.value = { wafer: [], die: [], reticle: [] };
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

function onBoxSelect(region: BoxSelectionRegion): void {
  emit("box-select", region);
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
</script>

<template>
  <div class="sc-map-panel" data-testid="sc-map-panel">
    <div v-if="effectiveMapError" class="sc-map-error">
      <NResult status="error" title="Map Error" :description="effectiveMapError">
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
          <NTooltip placement="bottom">
            <template #trigger>
              <NButton
                data-testid="sc-map-zoom-in-button"
                size="small"
                quaternary
                aria-label="Zoom in one step"
                @click="zoomBy(0.5)"
              >
                <template #icon
                  ><NIcon><AddOutline /></NIcon
                ></template>
              </NButton>
            </template>
            Zoom in one step
          </NTooltip>
          <NTooltip placement="bottom">
            <template #trigger>
              <NButton
                data-testid="sc-map-zoom-out-button"
                size="small"
                quaternary
                :disabled="zoom == null"
                aria-label="Zoom out one step"
                @click="zoomBy(2)"
              >
                <template #icon
                  ><NIcon><RemoveOutline /></NIcon
                ></template>
              </NButton>
            </template>
            Zoom out
          </NTooltip>
          <NTooltip placement="bottom">
            <template #trigger>
              <NButton
                data-testid="sc-map-pan-tool"
                size="small"
                quaternary
                :type="mapMode[internalTab] === 'pan' ? 'primary' : 'default'"
                aria-label="Pan map"
                @click="mapMode[internalTab] = 'pan'"
              >
                <template #icon
                  ><NIcon><MoveOutline /></NIcon
                ></template>
              </NButton>
            </template>
            Pan
          </NTooltip>
          <ScReticleMapOptionsButton
            :modelValue="effectiveReticleOptions"
            :show-image-markers="showImageMarkers"
            :defect-size="defectSize"
            size="small"
            icon-only
            quaternary
            @submit="handleReticleOptionsSubmit"
            @submit-display="handleMapDisplaySubmit"
          />
        </div>
      </div>

      <div class="sc-map-body" data-testid="sc-map-toolbar-container">
        <div class="map-area">
          <div v-if="effectiveMapLoading" class="map-loading-overlay">
            <NSpin size="small" />
            <NText depth="3" class="map-loading-text">
              {{ effectiveMapProgressMessage }}
            </NText>
          </div>
          <sc-map
            data-testid="sc-unified-map"
            :arrowData.prop="arrowData ?? null"
            :legendColumn.prop="mapLegendColumn ?? 'class_number'"
            :hiddenLegendKeys.prop="activeHiddenLegendKeys"
            :colorMap.prop="colorMap"
            :showImageMarkers.prop="showImageMarkers"
            :defectSize.prop="defectSize"
            :mode.prop="internalTab"
            :interactionMode.prop="mapMode[internalTab]"
            :zoom.prop="zoom ?? null"
            :geometry.prop="nativeGeometry"
            :highlights.prop="highlightDefects ?? []"
            :immediatePoints.prop="activeImmediatePoints"
            @zoom-in="onNativeZoom"
            @box-select="onNativeBoxSelect"
            @immediate-crosshair-points="onNativeImmediateCrosshair"
            @map-progress="onNativeMapProgress"
            @map-ready="onNativeMapReady"
            @map-error="onNativeMapError"
          />
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
