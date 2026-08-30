<script setup lang="ts">
import { computed, h, nextTick, ref, watch, type Component } from "vue";
import { useI18n } from "vue-i18n";
import {
  defineScMapElement,
  ScMapElement,
  type ScMapErrorDetail,
  type ScMapGeometry,
  type ScMapLassoSelection,
  type ScMapSelectionCommand,
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
import Legend from "./Legend.vue";
import ReticleMapOptionsButton from "./ReticleMapOptionsButton.vue";
import { legendColor } from "./scMapUtils";
import type { DefectList } from "../../generated/proto/sc/v1/sample_pb";
import type { ScMapSelectionMode } from "@/features/sc/domain/workbenchInteraction";

const { t } = useI18n();

if (import.meta.env.MODE !== "test") defineScMapElement();

type LegendSource = "class" | "bin" | "annotation" | "prediction" | "final_class";
type LegendKey = number | string;
type BoxSelectionRegion = { x: number; y: number; w: number; h: number };
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
    mapSelectionCount?: number;

    /** IDs resolved against the Arrow snapshot already retained by <sc-map>. */
    highlightDefectIds?: number[];
    selectionDefectIds?: number[];
    highlightMapIds?: number[];
    selectionMapIds?: number[];
    selectionResetVersion?: number;
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
  (e: "legend-select", keys: LegendKey[]): void;
  (e: "zoom-in", vp: { x: number; y: number; w: number; h: number } | null): void;
  (e: "retry"): void;
  (e: "clear-selection"): void;
  (e: "legend-group-change", groupBy: string | null): void;
  (e: "legend-hidden-change", payload: { source: LegendSource; hiddenKeys: string[] }): void;
  (e: "box-select", region: { x: number; y: number; w: number; h: number }): void;
  (e: "lasso-select", selection: ScMapLassoSelection): void;
  (e: "commit-map-selection-filter", mode: ScMapSelectionMode): void;
  (e: "invert-map-selection-mode"): void;
  (e: "copy-selected-defect-ids"): void;
  (e: "update:showImageMarkers", value: boolean): void;
  (e: "update:defectSize", value: number): void;
}>();

const internalTab = ref<MapTab>(props.activeMapTab ?? "wafer");
const nativeMapElement = ref<ScMapElement | null>(null);
const mapMode = ref<Record<MapTab, MapToolAction>>({
  wafer: "select",
  die: "select",
  reticle: "select",
});
const drawerVisible = ref<boolean>(!loadPersistedState("sc_map_panel.drawer_collapsed", false));
const nativeMapLoading = ref(false);
const nativeMapError = ref<string | null>(null);
const nativeMapProgressMessage = ref("");
const mapReadyWaiters = new Set<{
  resolve: () => void;
  reject: (error: Error) => void;
}>();
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
  internalTab.value = tab;
  selectedClassNumbers.value = [];
  emit("update:activeMapTab", tab);
};

const selectedClassNumbers = ref<LegendKey[]>([]);
const legendSource = ref<LegendSource>(props.legendGroupBy ?? "class");
function emptyHiddenLegendKeysBySource(): Record<LegendSource, string[]> {
  return { class: [], bin: [], annotation: [], prediction: [], final_class: [] };
}
const hiddenLegendKeysBySource = ref<Record<LegendSource, string[]>>(
  emptyHiddenLegendKeysBySource(),
);
const colorMapsBySource = ref<Record<LegendSource, Record<string, string>>>(emptyColorMaps());
const colorMap = computed(() => colorMapsBySource.value[legendSource.value]);
const legendSourceOptions = computed(() => {
  const enabled = props.legendSources ?? ["class", "bin"];
  const labels: Record<LegendSource, string> = {
    class: t("sc.class"),
    bin: t("sc.roughBin"),
    annotation: t("sc.annotation"),
    prediction: t("sc.latestPrediction"),
    final_class: t("sc.finalClass"),
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
  selectedClassNumbers.value = [];
});

watch(drawerVisible, (val) => {
  savePersistedState("sc_map_panel.drawer_collapsed", !val);
});

const handleZoomIn = (vp: { x: number; y: number; w: number; h: number } | null) => {
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

const mapSelectionToolOptions = computed<DropdownOption[]>(() => [
  {
    label: t("sc.boxSelectionAppend"),
    key: "select" satisfies MapToolAction,
    icon: mapToolIcon(ScanOutline),
  },
  {
    label: t("sc.lassoSelectionAppend"),
    key: "lasso" satisfies MapToolAction,
    icon: mapToolIcon(BrushOutline),
  },
]);
const mapNavigationToolOptions = computed<DropdownOption[]>(() => [
  {
    label: t("sc.dragToZoom"),
    key: "zoomin" satisfies MapToolAction,
    icon: mapToolIcon(SearchOutline),
  },
  {
    label: t("sc.panMap"),
    key: "pan" satisfies MapToolAction,
    icon: mapToolIcon(MoveOutline),
  },
]);
const mapToolOptions = computed<DropdownOption[]>(() => [
  ...mapSelectionToolOptions.value,
  ...mapNavigationToolOptions.value,
]);
const mapSelectionContextOptions = computed<DropdownOption[]>(() => [
  {
    label: t("sc.excludeAllOthers"),
    key: "include",
    disabled: !props.mapSelectionCount,
  },
  {
    label: t("sc.excludeSelected"),
    key: "exclude",
    disabled: !props.mapSelectionCount,
  },
  {
    label: t("sc.invertSelection"),
    key: "invert-selection",
    disabled: !props.mapSelectionCount,
  },
  {
    label: t("sc.copySelectedDefectIds"),
    key: "copy-selected-defect-ids",
    disabled: !props.mapSelectionCount,
  },
  {
    label: t("sc.selectionTool"),
    key: "selection-tool",
    children: mapSelectionToolOptions.value,
  },
  {
    label: t("sc.navigationTool"),
    key: "navigation-tool",
    children: mapNavigationToolOptions.value,
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
    emit("commit-map-selection-filter", action);
    return;
  }
  if (action === "invert-selection") {
    emit("invert-map-selection-mode");
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
    hiddenLegendKeysBySource.value = emptyHiddenLegendKeysBySource();
    emit("legend-hidden-change", { source: legendSource.value, hiddenKeys: [] });
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
  emit("clear-selection");
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
  nativeMapProgressMessage.value = t("sc.mapReady");
  for (const waiter of mapReadyWaiters) waiter.resolve();
  mapReadyWaiters.clear();
}

function onNativeMapError(event: Event): void {
  nativeMapLoading.value = false;
  keepMapVisibleWhileRendering.value = false;
  const detail = (event as CustomEvent<ScMapErrorDetail | string>).detail;
  nativeMapError.value =
    typeof detail === "string" ? detail : `${detail.context}: ${detail.message}`;
  const error = new Error(nativeMapError.value);
  for (const waiter of mapReadyWaiters) waiter.reject(error);
  mapReadyWaiters.clear();
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
    t("sc.loadingMap"),
);

watch(
  () => props.selectionResetVersion,
  () => {
    selectedClassNumbers.value = [];
  },
);

async function updateMapSelection(command: ScMapSelectionCommand): Promise<number[]> {
  await nextTick();
  if (nativeMapLoading.value) {
    await new Promise<void>((resolve, reject) => {
      mapReadyWaiters.add({ resolve, reject });
    });
  }
  const map = nativeMapElement.value;
  if (!map) throw new Error(t("sc.mapElementNotReady"));
  return map.updateSelection(command);
}

function clearMapSelection(): void {
  nativeMapElement.value?.clearSelection();
  selectedClassNumbers.value = [];
}

defineExpose({ updateMapSelection, clearMapSelection });

function onBoxSelect(region: BoxSelectionRegion): void {
  emit("box-select", region);
}

const handleLegendSelect = (keys: LegendKey[]) => {
  selectedClassNumbers.value = [...keys];
  emit("legend-select", keys);
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
      <NResult status="error" :title="t('sc.mapError')" :description="effectiveMapError">
        <template #footer>
          <NButton @click="handleRetry">{{ t("common.retry") }}</NButton>
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
          <NTabPane name="wafer" :tab="t('sc.wafer')" data-testid="sc-map-tab-wafer" />
          <NTabPane name="die" :tab="t('sc.dieStack')" data-testid="sc-map-tab-die" />
          <NTabPane name="reticle" :tab="t('sc.reticle')" data-testid="sc-map-tab-reticle" />
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
              :aria-label="t('sc.mapTools')"
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
            :aria-label="t('sc.zoomIn')"
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
            :aria-label="t('sc.zoomOut')"
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
            :aria-label="t('sc.resetZoom')"
            :disabled="zoom == null"
            @click="handleZoomIn(null)"
          >
            <template #icon>
              <NIcon><ContractOutline /></NIcon>
            </template>
          </NButton>
          <ReticleMapOptionsButton
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
            ref="nativeMapElement"
            data-testid="sc-unified-map"
            :title="t('sc.mapNavigationHelp')"
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
            :highlightMapIds.prop="highlightMapIds ?? highlightDefectIds ?? []"
            :selectionMapIds.prop="selectionMapIds ?? selectionDefectIds ?? []"
            @zoom-in="onNativeZoom"
            @box-select="onNativeBoxSelect"
            @lasso-select="onNativeLassoSelect"
            @map-context-menu="onNativeMapContextMenu"
            @pointerdown="onNativeMapPointerDown"
            @clear-selection="onNativeClearSelection"
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
              :tab="t('sc.legend')"
              data-testid="sc-legend-tab"
              style="flex: 1; min-height: 0; display: flex; flex-direction: column"
            >
              <div class="drawer-header">
                <NSelect
                  data-testid="sc-legend-source-select"
                  v-model:value="legendSource"
                  :options="legendSourceOptions"
                  size="small"
                  :placeholder="t('sc.source')"
                />
              </div>

              <div style="flex: 1; min-height: 0; overflow-y: auto">
                <Legend
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
                  :selectedClassNumbers="selectedClassNumbers"
                  :legendSource="legendSource"
                  :hidden-keys="activeHiddenLegendKeys"
                  @select-classes="handleLegendSelect"
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
