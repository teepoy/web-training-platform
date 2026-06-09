<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { NTabs, NTabPane, NSpin, NResult, NButton, NSelect, NIcon, NTooltip } from "naive-ui";
import { MenuOutline } from "@vicons/ionicons5";
import { ArrowBackOutline, ArrowForwardOutline } from "@vicons/ionicons5";
import { AddOutline, ScanOutline, SearchOutline } from "@vicons/ionicons5";
import ScWaferMap from "./ScWaferMap.vue";
import ScDieStackMap from "./ScDieStackMap.vue";
import ScReticleMap from "./ScReticleMap.vue";
import ScLegend from "./ScLegend.vue";
import ScReticleMapOptionsButton from "./ScReticleMapOptionsButton.vue";
import { parsePoints, getDefectIdsByClass, getDefectIdsByBin } from "./scMapUtils";
import type { ClassList, DefectList } from "../../generated/proto/sc/v1/sample_pb";

type LegendSource = "class" | "bin" | "annotation" | "prediction";
type LegendKey = number | string;
const UNLABELED_KEY = "__unlabeled__";
const NO_PREDICTION_KEY = "__no_prediction__";

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
  waferGeometry?: { centerX: number; centerY: number; originX: number; originY: number; dieSizeX: number; dieSizeY: number } | null;
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

  // Legend control (optional)
  legendPoints?: number[];
  legendSources?: LegendSource[];
  classList?: ClassList | null;
  selectedIds?: ReadonlySet<number>;

  // Zoom viewport
  zoom?: { x: number; y: number; w: number; h: number } | null;
}>();

const emit = defineEmits<{
  (e: "update:activeMapTab", v: "wafer" | "die" | "reticle"): void;
  (e: "update:reticleOptions", v: { xDieCount: number; yDieCount: number; xDieShift: number; yDieShift: number }): void;
  (e: "select-points", payload: { ids: number[]; region: { x: number; y: number; w: number; h: number } }): void;
  (e: "filter-region", payload: { mode: "wafer" | "die" | "reticle"; region: { x: number; y: number; w: number; h: number } }): void;
  (e: "zoom-in", vp: { x: number; y: number; w: number; h: number } | null): void;
  (e: "retry"): void;
}>();

const internalTab = ref<"wafer" | "die" | "reticle">(props.activeMapTab ?? "wafer");
const mapMode = ref<Record<string, "select" | "zoomin">>({ wafer: "select", die: "select", reticle: "select" });

// Sync prop to internal state
watch(() => props.activeMapTab, (newVal) => {
  if (newVal && newVal !== internalTab.value) {
    internalTab.value = newVal;
  }
});

const handleTabChange = (value: string | number) => {
  const tab = value as "wafer" | "die" | "reticle";
  emit("zoom-in", null);
  internalTab.value = tab;
  selectedClassNumber.value = null;
  emit("update:activeMapTab", tab);
};

const selectedClassNumber = ref<LegendKey | null>(null);
const selectedIds = ref<Set<number>>(new Set(props.selectedIds ?? []));
const legendSource = ref<LegendSource>("class");
const legendSourceOptions = computed(() => {
  const enabled = props.legendSources ?? ["class", "bin"];
  const labels: Record<LegendSource, string> = {
    class: "Class",
    bin: "Rough Bin",
    annotation: "Annotation",
    prediction: "Prediction (Latest)",
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

const toolbarVisible = ref<boolean>(!loadPersistedState("sc_map_panel.toolbar_collapsed", false));
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

watch(legendSource, () => {
  selectedClassNumber.value = null;
  selectedIds.value = new Set();
});

watch(toolbarVisible, (val) => {
  savePersistedState("sc_map_panel.toolbar_collapsed", !val);
});

watch(drawerVisible, (val) => {
  savePersistedState("sc_map_panel.drawer_collapsed", !val);
});

const handleFilterRegion = (region: { x: number; y: number; w: number; h: number }) => {
  selectedClassNumber.value = null;
  emit("filter-region", { mode: internalTab.value, region });
};

const handleZoomIn = (vp: { x: number; y: number; w: number; h: number } | null) => {
  emit("zoom-in", vp);
};

const handleRetry = () => {
  emit("retry");
};

const handleReticleOptionsSubmit = (opts: { xDieCount: number; yDieCount: number; xDieShift: number; yDieShift: number }) => {
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
const allDefectIds = computed(() => {
  const ids = new Set<number>();
  for (const group of Object.values(props.classList?.classNumbers ?? {})) {
    for (const id of group.defectIds) ids.add(id);
  }
  if (ids.size === 0) {
    for (const group of Object.values(props.classList?.roughBins ?? {})) {
      for (const id of group.defectIds) ids.add(id);
    }
  }
  if (ids.size === 0) {
    for (const point of parsedCache.value) ids.add(point.defectId);
  }
  return ids;
});

function groupsWithMissing(
  groups: Record<string, DefectList> | undefined,
  missingKey: string,
): Record<string, DefectList> {
  const result = { ...(groups ?? {}) };
  const assigned = new Set<number>();
  for (const group of Object.values(result)) {
    for (const id of group.defectIds) assigned.add(id);
  }
  const missingIds = [...allDefectIds.value].filter((id) => !assigned.has(id));
  if (missingIds.length > 0) {
    result[missingKey] = {
      $typeName: "sc.v1.DefectList",
      count: missingIds.length,
      defectIds: missingIds,
    };
  }
  return result;
}

const annotationGroups = computed(() =>
  groupsWithMissing(props.classList?.labels, UNLABELED_KEY),
);
const predictionGroups = computed(() =>
  groupsWithMissing(props.classList?.prediction, NO_PREDICTION_KEY),
);
const showWaferLoading = computed(
  () => Boolean(props.mapLoading) && (props.waferPoints?.length ?? 0) === 0,
);
const showDieLoading = computed(
  () => Boolean(props.mapLoading) && (props.diePoints?.length ?? 0) === 0,
);
const showReticleLoading = computed(
  () => Boolean(props.mapLoading) && (props.reticlePoints?.length ?? 0) === 0,
);

const ZERO_REGION = { x: 0, y: 0, w: 0, h: 0 };

const handleLegendSelect = (key: LegendKey | null) => {
  if (key === null) {
    selectedClassNumber.value = null;
    selectedIds.value = new Set();
    emit("select-points", { ids: [], region: ZERO_REGION });
  } else {
    selectedClassNumber.value = key;
    const compactGroups = {
      class: props.classList?.classNumbers,
      bin: props.classList?.roughBins,
      annotation: annotationGroups.value,
      prediction: predictionGroups.value,
    }[legendSource.value];
    const compactGroup = compactGroups?.[String(key)];
    const ids = compactGroup?.defectIds ?? (
      typeof key === "number"
        ? legendSource.value === "bin"
          ? getDefectIdsByBin(parsedCache.value, key)
          : getDefectIdsByClass(parsedCache.value, key)
        : []
    );
    selectedIds.value = new Set(ids);
    emit("select-points", { ids, region: ZERO_REGION });
  }
};
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
          <div class="map-tabs-row">
            <NTabs
              :value="internalTab"
              @update:value="handleTabChange"
              type="line"
              size="small"
              display-directive="show"
              style="flex: 1; min-height: 0; display: flex; flex-direction: column;"
            >
              <NTabPane name="wafer" tab="Wafer" data-testid="sc-map-tab-wafer">
            <NSpin :show="showWaferLoading">
              <ScWaferMap
                :points="waferPoints"
                :fullPoints="waferFullPoints"
                :geometry="waferGeometry"
                :waferRadiusNm="waferRadiusNm"
                :selectedIds="selectedIds"
                :zoom="zoom"
                :mode="mapMode.wafer"
                @filter-region="handleFilterRegion"
                @zoom-in="handleZoomIn"
              />
            </NSpin>
          </NTabPane>

          <NTabPane name="die" tab="Die Stack" data-testid="sc-map-tab-die">
            <NSpin :show="showDieLoading">
              <ScDieStackMap
                :points="diePoints"
                :fullPoints="dieFullPoints"
                :die-size-x="waferGeometry?.dieSizeX"
                :die-size-y="waferGeometry?.dieSizeY"
                :selectedIds="selectedIds"
                :zoom="zoom"
                :mode="mapMode.die"
                @filter-region="handleFilterRegion"
                @zoom-in="handleZoomIn"
              />
            </NSpin>
          </NTabPane>

          <NTabPane name="reticle" tab="Reticle" data-testid="sc-map-tab-reticle">
            <NSpin :show="showReticleLoading">
              <ScReticleMap
                v-if="reticleXDieCount !== undefined && reticleYDieCount !== undefined && reticleDieSizeX !== undefined && reticleDieSizeY !== undefined"
                :points="reticlePoints"
                :fullPoints="reticleFullPoints"
                :xDieCount="reticleXDieCount"
                :yDieCount="reticleYDieCount"
                :dieSizeX="reticleDieSizeX"
                :dieSizeY="reticleDieSizeY"
                :selectedIds="selectedIds"
                :zoom="zoom"
                :mode="mapMode.reticle"
                @filter-region="handleFilterRegion"
                @zoom-in="handleZoomIn"
              />
              <div v-else class="reticle-map-placeholder">
                Missing reticle configuration
              </div>
            </NSpin>

          </NTabPane>
        </NTabs>
          </div>
        <div class="floating-toolbar">
          <NButton
            data-testid="sc-map-toolbar-toggle"
            size="small"
            quaternary
            @click="toolbarVisible = !toolbarVisible"
            style="margin-bottom: 4px"
          >
            <template #icon><NIcon><MenuOutline /></NIcon></template>
          </NButton>
          <div v-show="toolbarVisible" class="floating-toolbar-actions">
            <NTooltip placement="right">
              <template #trigger>
                <NButton
                  data-testid="sc-map-select-tool"
                  size="small"
                  quaternary
                  :type="mapMode[internalTab] === 'select' ? 'primary' : 'default'"
                  aria-label="Box selection"
                  @click="mapMode[internalTab] = 'select'"
                >
                  <template #icon><NIcon><ScanOutline /></NIcon></template>
                </NButton>
              </template>
              Box selection
            </NTooltip>
            <NTooltip placement="right">
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
        :style="{ width: drawerVisible ? '130px' : '0px', minWidth: drawerVisible ? '130px' : '0px' }"
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

        <div class="drawer-header" v-show="drawerVisible">
          <NSelect
            data-testid="sc-legend-source-select"
            v-model:value="legendSource"
            :options="legendSourceOptions"
            size="small"
            placeholder="Source"
          />
        </div>

        <div v-show="drawerVisible" style="flex: 1; min-height: 0; overflow-y: auto;">
          <ScLegend
            :points="[]"
            :fullPoints="currentLegendPoints"
            :class-numbers="classList?.classNumbers"
            :rough-bins="classList?.roughBins"
            :annotations="annotationGroups"
            :predictions="predictionGroups"
            :selectedClassNumber="selectedClassNumber"
            :legendSource="legendSource"
            @select-class="handleLegendSelect"
          />
        </div>
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
  max-width: 800px;
  margin: 0 auto;
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

.floating-toolbar {
  position: absolute;
  top: calc(var(--sc-map-canvas-top) + 4px);
  left: 12px;
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.floating-toolbar-actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
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
