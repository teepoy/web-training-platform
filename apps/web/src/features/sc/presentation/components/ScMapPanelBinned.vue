<script setup lang="ts">
import { computed, h, nextTick, ref, watch, type Component } from "vue";
import {
  defineScMapElement,
  type ScMapErrorDetail,
  type ScMapGeometry,
  type ScMapLassoSelection,
} from "@platform/sc-map-element";
import {
  NTabs,
  NTabPane,
  NResult,
  NButton,
  NDropdown,
  NSelect,
  NIcon,
  NSpin,
  NText,
  type DropdownOption,
} from "naive-ui";
import { ArrowBackOutline, ArrowForwardOutline } from "@vicons/ionicons5";
import {
  AddOutline,
  BrushOutline,
  ContractOutline,
  MoveOutline,
  RemoveOutline,
  ScanOutline,
  SearchOutline,
} from "@vicons/ionicons5";
import ScLegend from "./ScLegend.vue";
import ScReticleMapOptionsButton from "./ScReticleMapOptionsButton.vue";
import { legendColor } from "./scMapUtils";
import type { DefectList } from "../../generated/proto/sc/v1/sample_pb";
import type { ScMapSelectionMode } from "@/features/sc/domain/workbenchInteraction";

if (import.meta.env.MODE !== "test") defineScMapElement();

type LegendSource = "class" | "bin" | "annotation" | "prediction" | "final_class";
type LegendKey = number | string;
type BoxSelectionRegion = { x: number; y: number; w: number; h: number };
type CrosshairPoint = { x: number; y: number };
type MapTab = "wafer" | "die" | "reticle";
type MapToolAction = "select" | "lasso" | "zoomin" | "pan";

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
    colorMapScopeKey?: string;

    zoom?: { x: number; y: number; w: number; h: number } | null;
    mapSelectionMode?: ScMapSelectionMode | null;
    mapSelectionCount?: number;
    canUndoMapSelectionMode?: boolean;

    /** IDs resolved against the Arrow snapshot already retained by <sc-map>. */
    highlightDefectIds?: number[];
    immediateCrosshairDefectIds?: number[];
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
  (e: "legend-select", key: LegendKey | null): void;
  (e: "zoom-in", vp: { x: number; y: number; w: number; h: number } | null): void;
  (e: "retry"): void;
  (e: "clear-selection"): void;
  (e: "legend-group-change", groupBy: string | null): void;
  (e: "legend-hidden-change", payload: { source: LegendSource; hiddenKeys: string[] }): void;
  (e: "box-select", region: { x: number; y: number; w: number; h: number }): void;
  (e: "lasso-select", selection: ScMapLassoSelection): void;
  (e: "update:mapSelectionMode", mode: ScMapSelectionMode): void;
  (e: "invert-map-selection-mode"): void;
  (e: "undo-map-selection-mode"): void;
  (e: "copy-selected-defect-ids"): void;
  (e: "update:showImageMarkers", value: boolean): void;
  (e: "update:defectSize", value: number): void;
}>();

const internalTab = ref<MapTab>(props.activeMapTab ?? "wafer");
const mapMode = ref<Record<MapTab, MapToolAction>>({
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
const colorMapsBySource = ref<Record<LegendSource, Record<string, string>>>(emptyColorMaps());
const colorMap = computed(() => colorMapsBySource.value[legendSource.value]);
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

function emptyColorMaps(): Record<LegendSource, Record<string, string>> {
  return {
    class: {},
    bin: {},
    annotation: {},
    prediction: {},
    final_class: {},
  };
}

function colorMapStorageKey(source: LegendSource): string | null {
  const scope = props.colorMapScopeKey?.trim();
  return scope ? `sc_map_panel.color_map.${encodeURIComponent(scope)}.${source}` : null;
}

function loadPersistedColorMap(source: LegendSource): Record<string, string> {
  const key = colorMapStorageKey(source);
  if (!key) return {};
  try {
    const parsed = JSON.parse(localStorage.getItem(key) ?? "{}") as Record<string, unknown>;
    return Object.fromEntries(
      Object.entries(parsed).filter(
        (entry): entry is [string, string] =>
          typeof entry[1] === "string" && /^#[0-9a-f]{6}$/i.test(entry[1]),
      ),
    );
  } catch {
    return {};
  }
}

function loadPersistedColorMaps(): Record<LegendSource, Record<string, string>> {
  return {
    class: loadPersistedColorMap("class"),
    bin: loadPersistedColorMap("bin"),
    annotation: loadPersistedColorMap("annotation"),
    prediction: loadPersistedColorMap("prediction"),
    final_class: loadPersistedColorMap("final_class"),
  };
}

function updateColorMap(source: LegendSource, next: Record<string, string>): void {
  colorMapsBySource.value = { ...colorMapsBySource.value, [source]: next };
  const key = colorMapStorageKey(source);
  if (key) localStorage.setItem(key, JSON.stringify(next));
}

function handleColorMapUpdate(next: Record<string, string>): void {
  updateColorMap(legendSource.value, next);
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

function mapToolIcon(icon: Component): () => ReturnType<typeof h> {
  return () => h(NIcon, null, { default: () => h(icon) });
}

const activeMapToolIcon = computed(() => {
  const mode = mapMode.value[internalTab.value];
  if (mode === "zoomin") return SearchOutline;
  if (mode === "lasso") return BrushOutline;
  if (mode === "pan") return MoveOutline;
  return ScanOutline;
});

const mapToolOptions = computed<DropdownOption[]>(() => [
  {
    label: "Box selection (append)",
    key: "select" satisfies MapToolAction,
    icon: mapToolIcon(ScanOutline),
  },
  {
    label: "Lasso selection (append)",
    key: "lasso" satisfies MapToolAction,
    icon: mapToolIcon(BrushOutline),
  },
  {
    label: "Drag to zoom",
    key: "zoomin" satisfies MapToolAction,
    icon: mapToolIcon(SearchOutline),
  },
  {
    label: "Pan map",
    key: "pan" satisfies MapToolAction,
    icon: mapToolIcon(MoveOutline),
  },
]);
const mapSelectionContextOptions = computed<DropdownOption[]>(() => [
  {
    label: "Exclude all others",
    key: "include",
    disabled: props.mapSelectionMode === "include" || !props.mapSelectionCount,
  },
  {
    label: "Exclude selected",
    key: "exclude",
    disabled: props.mapSelectionMode === "exclude" || !props.mapSelectionCount,
  },
  {
    label: "Invert selection",
    key: "invert-selection",
    disabled: !props.mapSelectionCount,
  },
  {
    label: "Copy selected defect IDs",
    key: "copy-selected-defect-ids",
    disabled: !props.mapSelectionCount,
  },
  { type: "divider", key: "selection-actions-divider" },
  {
    label: "Undo selection filter",
    key: "undo-selection-filter",
    disabled: !props.canUndoMapSelectionMode,
  },
  {
    label: "Selection tool",
    key: "selection-tool",
    children: mapToolOptions.value,
  },
]);
const mapSelectionContextVisible = ref(false);
const mapSelectionContextX = ref(0);
const mapSelectionContextY = ref(0);

function onNativeMapContextMenu(event: Event): void {
  const position = (event as CustomEvent<{ x: number; y: number }>).detail;
  mapSelectionContextVisible.value = false;
  mapSelectionContextX.value = position.x;
  mapSelectionContextY.value = position.y;
  void nextTick(() => {
    mapSelectionContextVisible.value = true;
  });
}

function onNativeMapPointerDown(event: PointerEvent): void {
  if (event.button === 0) mapSelectionContextVisible.value = false;
}

function handleMapSelectionContextSelect(key: string | number): void {
  const action = String(key);
  mapSelectionContextVisible.value = false;
  if (action === "include" || action === "exclude") {
    emit("update:mapSelectionMode", action);
    return;
  }
  if (action === "invert-selection") {
    emit("invert-map-selection-mode");
    return;
  }
  if (action === "undo-selection-filter") {
    emit("undo-map-selection-mode");
    return;
  }
  if (action === "copy-selected-defect-ids") {
    emit("copy-selected-defect-ids");
    return;
  }
  handleMapToolSelect(action);
}

function handleMapToolSelect(key: string | number): void {
  const action = String(key);
  if (action === "select" || action === "lasso" || action === "zoomin" || action === "pan") {
    mapMode.value[internalTab.value] = action;
  }
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
  () => props.colorMapScopeKey,
  () => {
    const loaded = loadPersistedColorMaps();
    const source = legendSource.value;
    loaded[source] = Object.fromEntries(
      Object.entries(defaultColorMap.value).map(([key, defaultColor]) => [
        key,
        loaded[source][key] ?? defaultColor,
      ]),
    );
    colorMapsBySource.value = loaded;
  },
  { immediate: true },
);

watch(
  defaultColorMap,
  (defaults) => {
    const source = legendSource.value;
    const stored = colorMapsBySource.value[source];
    updateColorMap(
      source,
      Object.fromEntries(
        Object.entries(defaults).map(([key, defaultColor]) => [key, stored[key] ?? defaultColor]),
      ),
    );
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
  return localImmediateCrosshairPoints.value[internalTab.value];
});

function onNativeZoom(event: Event): void {
  keepMapVisibleWhileRendering.value = true;
  handleZoomIn(
    (event as CustomEvent<{ x: number; y: number; w: number; h: number } | null>).detail,
  );
}

function onNativeBoxSelect(event: Event): void {
  onBoxSelect((event as CustomEvent<BoxSelectionRegion>).detail);
}

function onNativeLassoSelect(event: Event): void {
  emit("lasso-select", (event as CustomEvent<ScMapLassoSelection>).detail);
}

function onNativeClearSelection(): void {
  clearLocalImmediateCrosshair();
  emit("clear-selection");
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
  const detail = (event as CustomEvent<ScMapErrorDetail | string>).detail;
  nativeMapError.value =
    typeof detail === "string" ? detail : `${detail.context}: ${detail.message}`;
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

function onBoxSelect(region: BoxSelectionRegion): void {
  emit("box-select", region);
}

const handleLegendSelect = (key: LegendKey | null) => {
  selectedClassNumber.value = key;
  emit("legend-select", key);
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
          <NDropdown
            data-testid="sc-map-tools-dropdown"
            trigger="click"
            placement="bottom-end"
            :options="mapToolOptions"
            @select="handleMapToolSelect"
          >
            <NButton
              data-testid="sc-map-tools-button"
              size="small"
              quaternary
              type="primary"
              aria-label="Map tools"
            >
              <template #icon>
                <NIcon><component :is="activeMapToolIcon" /></NIcon>
              </template>
            </NButton>
          </NDropdown>
          <NButton
            data-testid="sc-map-zoom-in-button"
            size="small"
            quaternary
            type="primary"
            aria-label="Zoom in"
            @click="zoomBy(0.5)"
          >
            <template #icon>
              <NIcon><AddOutline /></NIcon>
            </template>
          </NButton>
          <NButton
            data-testid="sc-map-zoom-out-button"
            size="small"
            quaternary
            type="primary"
            aria-label="Zoom out"
            :disabled="zoom == null"
            @click="zoomBy(2)"
          >
            <template #icon>
              <NIcon><RemoveOutline /></NIcon>
            </template>
          </NButton>
          <NButton
            data-testid="sc-map-reset-zoom-button"
            size="small"
            quaternary
            type="primary"
            aria-label="Reset zoom"
            :disabled="zoom == null"
            @click="handleZoomIn(null)"
          >
            <template #icon>
              <NIcon><ContractOutline /></NIcon>
            </template>
          </NButton>
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
          <NDropdown
            data-testid="sc-map-selection-context-menu"
            trigger="manual"
            placement="bottom-start"
            :show="mapSelectionContextVisible"
            :x="mapSelectionContextX"
            :y="mapSelectionContextY"
            :options="mapSelectionContextOptions"
            @clickoutside="mapSelectionContextVisible = false"
            @select="handleMapSelectionContextSelect"
          />
          <div v-if="effectiveMapLoading" class="map-loading-overlay">
            <NSpin size="small" />
            <NText depth="3" class="map-loading-text">
              {{ effectiveMapProgressMessage }}
            </NText>
          </div>
          <sc-map
            data-testid="sc-unified-map"
            title="Right-drag or two-finger scroll to pan · Pinch to zoom"
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
            :highlightDefectIds.prop="highlightDefectIds ?? []"
            :immediateDefectIds.prop="immediateCrosshairDefectIds ?? []"
            :immediatePoints.prop="activeImmediatePoints"
            @zoom-in="onNativeZoom"
            @box-select="onNativeBoxSelect"
            @lasso-select="onNativeLassoSelect"
            @map-context-menu="onNativeMapContextMenu"
            @pointerdown="onNativeMapPointerDown"
            @clear-selection="onNativeClearSelection"
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
                  @update:color-map="handleColorMapUpdate"
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
</style>
