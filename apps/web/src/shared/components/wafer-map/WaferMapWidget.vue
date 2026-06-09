<!--
  WaferMapWidget — Canvas wafer scatter map widget for dashboard/sidebar.

  Wraps ScWaferMap to bridge between the widget system (accepts `data`/`config`
  props) and the ScWaferMap flat-array interface.

  Data format (injected by injectWaferPanelData):
    { inline: { points: WaferPoint[] } }
-->
<script setup lang="ts">
import { computed, inject, shallowRef } from "vue";
import { DATA_PIPELINE_KEY } from "@/shared/composables/useDataPipeline";
import type { WaferPoint } from "@/shared/types/components";
import ScWaferMap from "@/features/sc/presentation/components/ScWaferMap.vue";

const props = defineProps<{
  data?: Record<string, unknown> | null;
  config?: Record<string, unknown>;
  size?: "compact" | "normal" | "large";
}>();

const pipeline = inject(DATA_PIPELINE_KEY, null);
const waferNode = pipeline?.getNode("wafer-map");

const waferPoints = computed<WaferPoint[]>(() => {
  if (!props.data) return [];
  const raw = (props.data as Record<string, unknown>).inline ?? props.data;
  if (!raw || typeof raw !== "object") return [];
  const points = (raw as Record<string, unknown>).points;
  if (!Array.isArray(points)) return [];
  return points as WaferPoint[];
});

const idMapping = shallowRef<Map<number, string>>(new Map());

const flatPoints = computed<number[]>(() => {
  const pts = waferPoints.value;
  const flat: number[] = new Array(pts.length * 6);
  const map = new Map<number, string>();

  for (let i = 0; i < pts.length; i += 1) {
    const p = pts[i];
    const offset = i * 6;
    flat[offset] = p.x;
    flat[offset + 1] = p.y;
    flat[offset + 2] = i; // numeric id = array index
    flat[offset + 3] = -1; // class_number (unknown)
    flat[offset + 4] = 0; // rough_bin (unknown)
    flat[offset + 5] = 0; // has_review (unknown)
    map.set(i, p.id);
  }

  idMapping.value = map;
  return flat;
});

function onSelectPoints(payload: { ids: number[]; region: { x: number; y: number; w: number; h: number } }): void {
  if (!waferNode) return;
  const mapping = idMapping.value;
  const stringIds = payload.ids
    .map((id) => mapping.get(id))
    .filter((id): id is string => id !== undefined);
  waferNode.annotate("selected", stringIds);
}
</script>

<template>
  <ScWaferMap :points="flatPoints" @select-points="onSelectPoints" />
</template>
