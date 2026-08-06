<script setup lang="ts">
import { computed, ref } from "vue";
import { NButton, NTag, useMessage, useThemeVars } from "naive-ui";
import type { ScGlobalFilter } from "@/features/sc/domain/globalFilter";
import type {
  ScSamplingGroupPopulation,
  ScSamplingProgram,
} from "@/features/sc/domain/samplingRules";
import ReviewSamplingModal from "@/features/sc/presentation/components/ReviewSamplingModal.vue";

const message = useMessage();
const themeVars = useThemeVars();
const modalVisible = ref(true);
const loading = ref(false);
const scope = ref<"all" | "map" | "table">("all");
const sandboxThemeStyle = computed(() => ({
  "--cv-surface-subtle": themeVars.value.bodyColor,
  "--cv-card-bg": themeVars.value.cardColor,
  "--cv-text-secondary": themeVars.value.textColor3,
  "--cv-border": themeVars.value.borderColor,
}));

const globalFilter = ref<ScGlobalFilter>({
  combinator: "and",
  items: [
    {
      id: "sandbox-confidence",
      field: "confidence",
      condition: {
        filterType: "number",
        type: "inRange",
        filter: 0.65,
        filterTo: 1,
      },
      source: { kind: "manual" },
    },
  ],
});
const filterValueCatalog: Record<string, Array<string | number>> = {
  class_number: ["Scratch", "Particle", "Residue", "Unknown"],
  rough_bin: [1, 2, 3, 4],
  final_bin: ["A", "B", "C"],
  annotation_label: ["accepted", "rejected"],
};
const extraFilterDistinctValues = ref<Record<string, Array<string | number>>>({});
const extraFilterNumericRanges = ref<Record<string, { min: number; max: number } | null>>({});

function searchExtraFilterOptions(payload: { field: string; search: string }): void {
  const search = payload.search.trim().toLocaleLowerCase();
  extraFilterDistinctValues.value = {
    ...extraFilterDistinctValues.value,
    [payload.field]: (filterValueCatalog[payload.field] ?? []).filter((value) =>
      String(value).toLocaleLowerCase().includes(search),
    ),
  };
}

function requestExtraFilterRange(payload: { field: string; itemId?: string }): void {
  if (!payload.itemId) return;
  extraFilterNumericRanges.value = {
    ...extraFilterNumericRanges.value,
    [payload.itemId]: payload.field === "confidence" ? { min: 0, max: 1 } : { min: 0, max: 1000 },
  };
}

const program = ref<ScSamplingProgram>({
  extraFilterEnabled: true,
  conditional: {
    enabled: true,
    field: "class_number",
    value: "Unknown",
    limit: 45,
  },
  group: {
    enabled: true,
    field: "class_number",
    unit: "ratio",
    targets: [
      { value: "Scratch", amount: 40 },
      { value: "Particle", amount: 30 },
      { value: "Residue", amount: 20 },
      { value: "Unknown", amount: 10 },
    ],
    othersAmount: 5,
    rounding: "nearest",
  },
  total: {
    enabled: true,
    limit: 200,
  },
});

const populations: ScSamplingGroupPopulation[] = [
  { value: "Scratch", count: 921 },
  { value: "Particle", count: 486 },
  { value: "Residue", count: 179 },
  { value: "Unknown", count: 45 },
];

async function loadGroups(): Promise<ScSamplingGroupPopulation[]> {
  return populations.map((group) => ({ ...group }));
}

function applySampling(): void {
  modalVisible.value = false;
  message.success("Sampling rules saved.");
}
</script>

<template>
  <main class="sandbox-host" :style="sandboxThemeStyle">
    <section class="sandbox-launcher">
      <NTag size="small">Sandbox host · not part of the modal</NTag>
      <h1>Review Sampling</h1>
      <p>
        This page only launches the production modal. Everything inside the dimmed overlay belongs
        to the modal.
      </p>
      <NButton type="primary" @click="modalVisible = true">Open Review Sampling modal</NButton>
    </section>

    <ReviewSamplingModal
      v-model:show="modalVisible"
      v-model:program="program"
      v-model:scope="scope"
      :loading="loading"
      :available-count="1631"
      :map-selection-count="0"
      :table-selection-available="false"
      v-model:extra-filter="globalFilter"
      :extra-filter-distinct-values="extraFilterDistinctValues"
      :extra-filter-numeric-ranges="extraFilterNumericRanges"
      :load-groups="loadGroups"
      @scope-change="message.info('Candidate scope updated.')"
      @search-extra-filter-options="searchExtraFilterOptions"
      @request-extra-filter-range="requestExtraFilterRange"
      @confirm="applySampling"
    />
  </main>
</template>

<style scoped>
.sandbox-host {
  min-height: calc(100vh - 56px);
  padding: 32px;
  background: var(--cv-surface-subtle, #f5f6f8);
}

.sandbox-launcher {
  width: min(460px, 100%);
  padding: 24px;
  background: var(--cv-card-bg, #fff);
  border: 1px solid var(--cv-border, #e2e5e9);
  border-radius: 10px;
}

.sandbox-launcher h1 {
  margin: 14px 0 6px;
  font-size: 24px;
}

.sandbox-launcher p {
  margin: 0 0 20px;
  color: var(--cv-text-secondary, #666);
  line-height: 1.55;
}

@media (max-width: 700px) {
  .sandbox-host {
    padding: 16px;
  }
}
</style>
