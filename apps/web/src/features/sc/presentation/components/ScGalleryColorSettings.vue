<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { NSelect, NSlider, NSwitch, NText } from "naive-ui";
import {
  colorBarBackground,
  GRAY_LUT_OPTIONS,
  nativeGrayWindow,
  type GrayLUT,
} from "./scGalleryToneMapping";

const props = defineProps<{
  enabled: boolean;
  lut: GrayLUT;
  zMin: number;
  zMax: number;
  bitDepth: 8 | 12 | 16;
  patches?: Array<{ label: string; bit_depth: 8 | 12 | 16; z_min: number; z_max: number }>;
  compact?: boolean;
}>();

const emit = defineEmits<{
  "update:enabled": [value: boolean];
  "update:lut": [value: GrayLUT];
  "update:zMin": [value: number];
  "update:zMax": [value: number];
}>();

const draftWindow = ref<[number, number]>([props.zMin, props.zMax]);
const colorBarStyle = computed(() => ({
  background: colorBarBackground(props.lut, draftWindow.value[0], draftWindow.value[1]),
}));
const draftToneMapping = computed(() => ({
  zMin: draftWindow.value[0],
  zMax: draftWindow.value[1],
}));
const nativeWindow = computed(() => nativeGrayWindow(draftToneMapping.value, props.bitDepth));

watch(
  () => [props.zMin, props.zMax] as const,
  ([zMin, zMax]) => {
    draftWindow.value = [zMin, zMax];
  },
);

function updateWindow(value: number | [number, number]): void {
  if (!Array.isArray(value)) return;
  const [zMin, zMax] = value;
  if (!Number.isFinite(zMin) || !Number.isFinite(zMax) || zMin >= zMax) return;
  draftWindow.value = [zMin, zMax];
}

function commitWindow(): void {
  const [zMin, zMax] = draftWindow.value;
  if (zMin !== props.zMin) emit("update:zMin", zMin);
  if (zMax !== props.zMax) emit("update:zMax", zMax);
}
</script>

<template>
  <div class="gallery-color-settings" :class="{ 'gallery-color-settings--compact': compact }">
    <div class="gallery-color-row">
      <div>
        <n-text class="gallery-color-label">Apply grayscale LUT</n-text>
      </div>
      <n-switch
        :value="enabled"
        size="small"
        data-testid="gallery-gray-mapping-toggle"
        @update:value="emit('update:enabled', $event)"
      />
    </div>

    <div class="gallery-color-field">
      <n-text class="gallery-color-label">Color map</n-text>
      <n-select
        :value="lut"
        size="small"
        :options="[...GRAY_LUT_OPTIONS]"
        :disabled="!enabled"
        data-testid="gallery-gray-lut"
        @update:value="emit('update:lut', $event as GrayLUT)"
      />
    </div>

    <div class="gallery-color-bar" :class="{ 'gallery-color-bar--disabled': !enabled }">
      <n-text class="gallery-color-label">{{ bitDepth }}-bit window</n-text>
      <div class="gallery-color-slider" :style="colorBarStyle" data-testid="gallery-color-bar">
        <n-slider
          :value="draftWindow"
          range
          :min="0"
          :max="1"
          :step="0.001"
          :disabled="!enabled"
          :format-tooltip="(value: number) => value.toFixed(3)"
          aria-label="Normalized grayscale window"
          @update:value="updateWindow"
          @dragend="commitWindow"
          @keyup="commitWindow"
        />
      </div>
      <div class="gallery-color-scale">
        <n-text depth="3">{{ draftWindow[0].toFixed(3) }}</n-text>
        <n-text depth="3">{{ draftWindow[1].toFixed(3) }}</n-text>
      </div>
    </div>

    <div class="gallery-color-native-values">
      <n-text depth="3">
        {{ nativeWindow.min.toLocaleString() }}–{{ nativeWindow.max.toLocaleString() }}
      </n-text>
    </div>
    <div v-if="patches?.length" class="gallery-color-profiles">
      <div v-for="patch in patches" :key="patch.label" class="gallery-color-profile">
        <n-text>{{ patch.label }}</n-text>
        <n-text depth="3">
          {{ patch.bit_depth }}-bit · {{ patch.z_min.toLocaleString() }}–{{
            patch.z_max.toLocaleString()
          }}
        </n-text>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gallery-color-settings {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gallery-color-settings--compact {
  gap: 12px;
}

.gallery-color-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.gallery-color-row > div,
.gallery-color-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.gallery-color-label {
  font-size: 12px;
  font-weight: 600;
}

.gallery-color-help,
.gallery-color-native-values,
.gallery-color-scale {
  font-size: 11px;
}

.gallery-color-profiles {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding-top: 8px;
  border-top: 1px solid rgba(128, 128, 128, 0.24);
}

.gallery-color-profile {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.gallery-color-bar {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.gallery-color-bar--disabled {
  opacity: 0.45;
}

.gallery-color-slider {
  height: 20px;
  padding: 0 8px;
  border: 1px solid rgba(128, 128, 128, 0.38);
  border-radius: 6px;
}

.gallery-color-slider :deep(.n-slider) {
  height: 18px;
}

.gallery-color-slider :deep(.n-slider-rail) {
  background: transparent;
}

.gallery-color-slider :deep(.n-slider-rail__fill) {
  background: rgba(255, 255, 255, 0.18);
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.38);
}

.gallery-color-scale,
.gallery-color-native-values {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-variant-numeric: tabular-nums;
}
</style>
