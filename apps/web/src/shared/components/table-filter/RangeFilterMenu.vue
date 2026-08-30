<script setup lang="ts">
import { computed } from "vue";
import { NDatePicker, NInputNumber, NSlider, NText } from "naive-ui";
import { useI18n } from "vue-i18n";
import TableFilterPopover from "./TableFilterPopover.vue";
import type { RangeFilterDescriptor } from "./rangeFilter";

const props = defineProps<{
  descriptor: RangeFilterDescriptor;
  min: number | null;
  max: number | null;
  loading?: boolean;
  rangeUnavailable?: boolean;
}>();
const { t } = useI18n();

const numericBounds = computed(() =>
  props.descriptor.kind === "number" ? props.descriptor.bounds : null,
);
const numericSliderValue = computed<[number, number] | undefined>(() =>
  props.descriptor.kind === "number" && props.min !== null && props.max !== null
    ? [props.min, props.max]
    : undefined,
);
const dateTimeValue = computed<[number, number] | null>(() =>
  props.descriptor.kind === "datetime" && props.min !== null && props.max !== null
    ? [props.min, props.max]
    : null,
);
const canApply = computed(() => {
  if (props.min === null && props.max === null) return true;
  if (
    props.min === null ||
    props.max === null ||
    !Number.isFinite(props.min) ||
    !Number.isFinite(props.max)
  ) {
    return false;
  }
  if (props.descriptor.kind === "datetime") return props.min < props.max;
  const bounds = props.descriptor.bounds;
  return (
    props.min <= props.max && (!bounds || (props.min >= bounds.min && props.max <= bounds.max))
  );
});

const emit = defineEmits<{
  (e: "update:min", value: number | null): void;
  (e: "update:max", value: number | null): void;
  (e: "apply"): void;
  (e: "close"): void;
}>();

function apply(): void {
  if (!canApply.value) return;
  emit("apply");
  emit("close");
}

function clear(): void {
  emit("update:min", null);
  emit("update:max", null);
}

function updateNumericSlider(value: number | number[]): void {
  if (!Array.isArray(value) || value.length !== 2) return;
  const [min, max] = value;
  if (!Number.isFinite(min) || !Number.isFinite(max)) return;
  emit("update:min", min!);
  emit("update:max", max!);
}

function updateDateTimeRange(value: number | [number, number] | null): void {
  if (!Array.isArray(value)) {
    clear();
    return;
  }
  emit("update:min", value[0]);
  emit("update:max", value[1]);
}

function formatSliderValue(value: number): string {
  if (props.descriptor.kind !== "number") return String(value);
  return new Intl.NumberFormat(undefined, {
    minimumFractionDigits: props.descriptor.displayPrecision,
    maximumFractionDigits: props.descriptor.displayPrecision,
  }).format(value);
}

function cancel(): void {
  emit("close");
}
</script>

<template>
  <TableFilterPopover
    variant="range"
    :apply-disabled="loading || !canApply"
    @clear="clear"
    @cancel="cancel"
    @apply="apply"
  >
    <NText v-if="loading" depth="3" class="sst-range-status">
      {{ t("tableFilters.queryingRange") }}
    </NText>
    <NText v-else-if="rangeUnavailable" type="error" class="sst-range-status">
      {{ t("tableFilters.rangeUnavailable") }}
    </NText>
    <template v-if="descriptor.kind === 'number'">
      <NSlider
        v-if="numericBounds && numericSliderValue"
        range
        :keyboard="true"
        :value="numericSliderValue"
        :min="numericBounds.min"
        :max="numericBounds.max"
        :step="descriptor.step"
        :format-tooltip="formatSliderValue"
        :disabled="
          loading || numericSliderValue === undefined || numericBounds.min === numericBounds.max
        "
        :aria-label="t('tableFilters.numericRangeSlider')"
        data-testid="numeric-range-slider"
        @update:value="updateNumericSlider"
      />
      <div class="sst-range-fields">
        <label class="sst-range-field">
          <NText depth="3" class="sst-range-label">{{ t("common.min") }}</NText>
          <NInputNumber
            :value="min"
            :placeholder="t('common.min')"
            size="small"
            class="sst-range-input"
            :min="numericBounds?.min"
            :max="numericBounds?.max"
            :step="descriptor.step"
            :disabled="loading"
            :aria-label="t('tableFilters.minimumValue')"
            @update:value="emit('update:min', $event)"
          />
        </label>
        <label class="sst-range-field">
          <NText depth="3" class="sst-range-label">{{ t("common.max") }}</NText>
          <NInputNumber
            :value="max"
            :placeholder="t('common.max')"
            size="small"
            class="sst-range-input"
            :min="numericBounds?.min"
            :max="numericBounds?.max"
            :step="descriptor.step"
            :disabled="loading"
            :aria-label="t('tableFilters.maximumValue')"
            @update:value="emit('update:max', $event)"
          />
        </label>
      </div>
    </template>
    <label v-else class="sst-range-field sst-datetime-range-field">
      <NText depth="3" class="sst-range-label">{{ t("tableFilters.dateTimeRange") }}</NText>
      <NDatePicker
        :value="dateTimeValue"
        type="datetimerange"
        clearable
        :disabled="loading"
        :start-placeholder="t('tableFilters.startDateTime')"
        :end-placeholder="t('tableFilters.endDateTime')"
        :aria-label="t('tableFilters.dateTimeRange')"
        data-testid="datetime-range-picker"
        @update:value="updateDateTimeRange"
      />
      <NText depth="3" class="sst-range-contract">
        {{ t("tableFilters.dateTimeRangeContract", { interval: descriptor.interval }) }}
      </NText>
    </label>
  </TableFilterPopover>
</template>

<style scoped>
.sst-range-input {
  width: 128px;
}

.sst-range-fields {
  display: flex;
  gap: 8px;
}

.sst-datetime-range-field {
  min-width: min(420px, calc(100vw - 64px));
}

.sst-range-field {
  display: grid;
  gap: 3px;
}

.sst-range-label {
  font-size: 11px;
}

.sst-range-status {
  max-width: 240px;
  font-size: 11px;
}

.sst-range-contract {
  font-size: 11px;
}
</style>
