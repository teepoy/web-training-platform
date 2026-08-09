<script setup lang="ts">
import { computed, ref, useSlots, watch } from "vue";
import {
  NAlert,
  NButton,
  NCard,
  NInputNumber,
  NModal,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NSpin,
  NTabPane,
  NTag,
  NTabs,
  NText,
  useMessage,
  useThemeVars,
} from "naive-ui";
import type { ScGlobalFilter } from "@/features/sc/domain/globalFilter";
import type { ScSamplingCandidateScope } from "@/features/sc/application/inspectionFilterPolicy";
import {
  cloneScSamplingProgram,
  SC_SAMPLING_GROUP_FIELDS,
  scSamplingProgramError,
  type ScSamplingGroupPopulation,
  type ScSamplingProgram,
  type ScSamplingRuleId,
} from "@/features/sc/domain/samplingRules";
import { scMissingFilterOption } from "@/features/sc/domain/missingFilterValue";
import ScGlobalFilterBar from "./ScGlobalFilterBar.vue";

interface RuleCatalogItem {
  id: ScSamplingRuleId;
  order: string;
  title: string;
  description: string;
}

const props = withDefaults(
  defineProps<{
    show: boolean;
    loading: boolean;
    availableCount: number;
    mapSelectionCount: number;
    tableSelectionAvailable: boolean;
    extraFilter: ScGlobalFilter;
    extraFilterDistinctValues?: Record<string, Array<string | number>>;
    extraFilterNumericRanges?: Record<string, { min: number; max: number } | null>;
    extraFilterNumericRangeLoading?: Record<string, boolean>;
    extraFilterNumericRangeErrors?: Record<string, boolean>;
    extraFilterResetKey?: string | number;
    confirmDisabled?: boolean;
    program: ScSamplingProgram;
    scope: ScSamplingCandidateScope;
    loadGroups: (field: string) => Promise<ScSamplingGroupPopulation[]>;
  }>(),
  {
    extraFilterDistinctValues: () => ({}),
    extraFilterNumericRanges: () => ({}),
    extraFilterNumericRangeLoading: () => ({}),
    extraFilterNumericRangeErrors: () => ({}),
    confirmDisabled: false,
  },
);

const emit = defineEmits<{
  (e: "update:show", show: boolean): void;
  (e: "update:program", program: ScSamplingProgram): void;
  (e: "update:scope", value: ScSamplingCandidateScope): void;
  (e: "update:extra-filter", filter: ScGlobalFilter): void;
  (e: "scope-change"): void;
  (e: "search-extra-filter-options", payload: { field: string; search: string }): void;
  (e: "request-extra-filter-range", payload: { field: string; itemId?: string }): void;
  (e: "confirm"): void;
}>();

const catalog: RuleCatalogItem[] = [
  {
    id: "extra",
    order: "01",
    title: "Extra filter",
    description: "Optionally narrow the selected candidate scope before applying limits.",
  },
  {
    id: "conditional",
    order: "02",
    title: "Conditional limit",
    description: "Cap only one matching subset while leaving other candidates eligible.",
  },
  {
    id: "quota",
    order: "03",
    title: "Group quota",
    description: "Choose a count or sample ratio for each group and for all other values.",
  },
  {
    id: "total",
    order: "04",
    title: "Total limit",
    description: "Cap the final cohort without implicitly filling shortfalls.",
  },
];

const message = useMessage();
const themeVars = useThemeVars();
const slots = useSlots();
const draft = ref(cloneScSamplingProgram(props.program));
const activeTab = ref<"rules" | "extra" | "after">("rules");
const manageRulesVisible = ref(false);
const ruleConfigVisible = ref(false);
const editingRule = ref<ScSamplingRuleId | null>(null);
const selectedDisabledRule = ref<ScSamplingRuleId | null>(null);
const selectedEnabledRule = ref<ScSamplingRuleId | null>(null);
const conditionalGroups = ref<ScSamplingGroupPopulation[]>([]);
const groupPopulations = ref<ScSamplingGroupPopulation[]>([]);
const conditionalGroupsLoading = ref(false);
const groupPopulationsLoading = ref(false);
let conditionalLoadVersion = 0;
let groupLoadVersion = 0;

const modalThemeStyle = computed(() => ({
  "--cv-bg": themeVars.value.bodyColor,
  "--cv-card-bg": themeVars.value.cardColor,
  "--cv-text": themeVars.value.textColor1,
  "--cv-text-secondary": themeVars.value.textColor3,
  "--cv-border": themeVars.value.borderColor,
  "--cv-divider": themeVars.value.dividerColor,
  "--cv-hover": themeVars.value.hoverColor,
  "--cv-primary": themeVars.value.primaryColor,
}));
const reviewModalStyle = computed(() => ({
  ...modalThemeStyle.value,
  width: "min(960px, calc(100vw - 32px))",
  maxHeight: "calc(100vh - 32px)",
  overflow: "auto",
}));
const manageModalStyle = computed(() => ({
  ...modalThemeStyle.value,
  width: "min(820px, calc(100vw - 32px))",
  maxHeight: "calc(100vh - 32px)",
  overflow: "auto",
}));
const ruleModalStyle = computed(() => ({
  ...modalThemeStyle.value,
  width: "min(760px, calc(100vw - 32px))",
  maxHeight: "calc(100vh - 32px)",
  overflow: "auto",
}));

const showModel = computed({
  get: () => props.show,
  set: (show: boolean) => emit("update:show", show),
});
const scopeModel = computed({
  get: () => props.scope,
  set: (value: ScSamplingCandidateScope) => emit("update:scope", value),
});
function ruleIsEnabled(id: ScSamplingRuleId): boolean {
  if (id === "extra") return draft.value.extraFilterEnabled;
  if (id === "conditional") return draft.value.conditional.enabled;
  if (id === "total") return draft.value.total.enabled;
  return draft.value.group.enabled;
}

const disabledRules = computed(() => catalog.filter((item) => !ruleIsEnabled(item.id)));
const enabledRules = computed(() => catalog.filter((item) => ruleIsEnabled(item.id)));
const configuredRules = computed(() => enabledRules.value.filter((item) => item.id !== "extra"));
const hasAfterSamplingTab = computed(() => Boolean(slots["after-sampling"]));
const configurationError = computed(() => scSamplingProgramError(draft.value));
const editingRuleItem = computed(
  () => catalog.find((item) => item.id === editingRule.value) ?? null,
);

const finalEstimate = computed(() => {
  let eligible = props.availableCount;
  if (draft.value.conditional.enabled) {
    const population = conditionalGroups.value.find(
      (group) => group.value === draft.value.conditional.value,
    )?.count;
    if (population !== undefined) {
      eligible -= Math.max(population - draft.value.conditional.limit, 0);
    }
  }
  if (draft.value.group.enabled && groupPopulations.value.length > 0) {
    eligible = groupPopulations.value.reduce((sum, population) => {
      const amount =
        draft.value.group.targets.find((target) => target.value === population.value)?.amount ??
        draft.value.group.othersAmount;
      const planned =
        draft.value.group.unit === "ratio"
          ? roundedCount(population.count * (amount / 100), draft.value.group.rounding)
          : amount;
      return sum + Math.min(population.count, planned);
    }, 0);
  }
  return draft.value.total.enabled ? Math.min(eligible, draft.value.total.limit) : eligible;
});

function roundedCount(value: number, rounding: "floor" | "ceil" | "nearest"): number {
  if (rounding === "floor") return Math.floor(value);
  if (rounding === "ceil") return Math.ceil(value);
  return Math.floor(value + 0.5);
}

function displayGroupValue(field: string, value: string): string {
  const missing = scMissingFilterOption(field);
  return missing?.value === value ? missing.label : value;
}

function defaultTargetAmount(population: ScSamplingGroupPopulation, count: number): number {
  if (draft.value.group.unit === "ratio") return 10;
  return Math.min(population.count, Math.max(Math.floor(draft.value.total.limit / count), 1));
}

function reconcileTargets(populations: ScSamplingGroupPopulation[], reset = false): void {
  const existing = new Map(
    (reset ? [] : draft.value.group.targets).map((target) => [target.value, target.amount]),
  );
  draft.value.group.targets = populations.map((population) => ({
    value: population.value,
    amount: existing.get(population.value) ?? defaultTargetAmount(population, populations.length),
  }));
  if (reset) draft.value.group.othersAmount = draft.value.group.unit === "ratio" ? 10 : 0;
}

async function loadConditionalGroups(): Promise<void> {
  if (!props.show) return;
  const version = ++conditionalLoadVersion;
  conditionalGroupsLoading.value = true;
  try {
    const groups = await props.loadGroups(draft.value.conditional.field);
    if (version !== conditionalLoadVersion) return;
    conditionalGroups.value = groups;
    if (!groups.some((group) => group.value === draft.value.conditional.value)) {
      draft.value.conditional.value = groups[0]?.value ?? "";
    }
  } catch (error) {
    if (version === conditionalLoadVersion) {
      message.error(error instanceof Error ? error.message : "Failed to load conditional groups");
    }
  } finally {
    if (version === conditionalLoadVersion) conditionalGroupsLoading.value = false;
  }
}

async function loadGroupPopulations(reset = false): Promise<void> {
  if (!props.show) return;
  const version = ++groupLoadVersion;
  groupPopulationsLoading.value = true;
  try {
    const groups = await props.loadGroups(draft.value.group.field);
    if (version !== groupLoadVersion) return;
    groupPopulations.value = groups;
    reconcileTargets(groups, reset);
  } catch (error) {
    if (version === groupLoadVersion) {
      message.error(error instanceof Error ? error.message : "Failed to load sampling groups");
    }
  } finally {
    if (version === groupLoadVersion) groupPopulationsLoading.value = false;
  }
}

function setRuleEnabled(id: ScSamplingRuleId, enabled: boolean): void {
  if (id === "extra") {
    draft.value.extraFilterEnabled = enabled;
    emit("update:program", cloneScSamplingProgram(draft.value));
    emit("scope-change");
  } else if (id === "conditional") {
    draft.value.conditional.enabled = enabled;
  } else if (id === "total") {
    draft.value.total.enabled = enabled;
  } else if (enabled) {
    draft.value.group.enabled = true;
    void loadGroupPopulations(true);
  } else if (draft.value.group.enabled && id === "quota") {
    draft.value.group.enabled = false;
  }
  selectedDisabledRule.value = null;
  selectedEnabledRule.value = enabled ? id : null;
}

function moveSelectedRule(enabled: boolean): void {
  const id = enabled ? selectedDisabledRule.value : selectedEnabledRule.value;
  if (id) setRuleEnabled(id, enabled);
}

function openRuleConfiguration(id: ScSamplingRuleId): void {
  if (id === "extra") {
    activeTab.value = "extra";
    return;
  }
  editingRule.value = id;
  ruleConfigVisible.value = true;
}

function handleScopeChange(): void {
  emit("scope-change");
  void loadConditionalGroups();
  void loadGroupPopulations();
}

function updateExtraFilter(filter: ScGlobalFilter): void {
  emit("update:extra-filter", filter);
  handleScopeChange();
}

function handleGroupModeChange(): void {
  void loadGroupPopulations(true);
}

function handleConfirm(): void {
  const error = configurationError.value;
  if (error) {
    message.error(error);
    return;
  }
  emit("update:program", cloneScSamplingProgram(draft.value));
  emit("confirm");
}

watch(
  () => props.show,
  (show) => {
    if (!show) return;
    draft.value = cloneScSamplingProgram(props.program);
    activeTab.value = "rules";
    void Promise.all([loadConditionalGroups(), loadGroupPopulations()]);
  },
  { immediate: true },
);

watch(draft, (program) => emit("update:program", cloneScSamplingProgram(program)), { deep: true });

watch(
  () => draft.value.conditional.field,
  () => void loadConditionalGroups(),
);

watch(
  () => draft.value.group.field,
  () => void loadGroupPopulations(true),
);
</script>

<template>
  <NModal
    v-model:show="showModel"
    preset="card"
    title="Review Sampling"
    :bordered="false"
    :style="reviewModalStyle"
    class="review-sampling-modal"
    data-testid="review-sampling-modal"
  >
    <NTabs v-model:value="activeTab" type="line" animated>
      <NTabPane name="rules" tab="Enabled rules">
        <NCard size="small" :bordered="false" class="scope-card">
          <div class="scope-heading">
            <div>
              <strong>Candidate scope</strong>
              <small>Choose one source before enabled sampling rules.</small>
            </div>
            <NText depth="3">{{ availableCount.toLocaleString() }} available</NText>
          </div>
          <NRadioGroup
            v-model:value="scopeModel"
            size="small"
            class="scope-options"
            @update:value="handleScopeChange"
          >
            <NRadioButton value="all">All</NRadioButton>
            <NRadioButton value="map" :disabled="mapSelectionCount === 0">
              Map Selection<span v-if="mapSelectionCount > 0"> ({{ mapSelectionCount }})</span>
            </NRadioButton>
            <NRadioButton value="table" :disabled="!tableSelectionAvailable">
              Table Selection
            </NRadioButton>
          </NRadioGroup>
        </NCard>

        <div class="rules-heading">
          <div>
            <strong>Active pipeline</strong>
            <small>Simple limits stay editable here; open complex rules for details.</small>
          </div>
          <NButton secondary type="primary" @click="manageRulesVisible = true">
            Manage sampling rules
          </NButton>
        </div>

        <div class="enabled-rule-list">
          <article v-for="item in configuredRules" :key="item.id" class="enabled-rule-item">
            <button
              v-if="item.id !== 'total'"
              type="button"
              class="rule-copy"
              @click="openRuleConfiguration(item.id)"
            >
              <span>{{ item.order }}</span>
              <div>
                <strong>{{ item.title }}</strong>
                <small>{{ item.description }}</small>
              </div>
            </button>
            <div v-else class="rule-copy rule-copy-static">
              <span>{{ item.order }}</span>
              <div>
                <strong>{{ item.title }}</strong>
                <small>{{ item.description }}</small>
              </div>
            </div>
            <div class="inline-control">
              <template v-if="item.id === 'conditional'">
                <label>Matched max</label>
                <NInputNumber
                  v-model:value="draft.conditional.limit"
                  :min="0"
                  :precision="0"
                  aria-label="Conditional limit"
                />
              </template>
              <template v-else-if="item.id === 'total'">
                <label>Final max</label>
                <NInputNumber
                  v-model:value="draft.total.limit"
                  :min="1"
                  :precision="0"
                  aria-label="Total limit"
                  data-testid="sampling-total-limit"
                />
              </template>
              <template v-else>
                <label>Configuration</label>
                <NTag size="small" type="success">
                  {{ draft.group.targets.length }} groups + Others ·
                  {{ draft.group.unit === "ratio" ? "sample ratio" : "count" }}
                </NTag>
              </template>
            </div>
            <NButton
              v-if="item.id !== 'total'"
              size="small"
              secondary
              @click="openRuleConfiguration(item.id)"
            >
              Edit
            </NButton>
          </article>
          <div v-if="configuredRules.length === 0" class="empty-rules">
            No limiting rule enabled. Use Manage sampling rules to add one.
          </div>
        </div>
      </NTabPane>

      <NTabPane name="extra" tab="Extra filter">
        <NCard :bordered="false" class="global-filter-card">
          <div class="global-filter-heading">
            <div>
              <strong>Extra filter</strong>
              <small>
                Apply an additional filter after choosing All, Map Selection, or Table Selection.
              </small>
            </div>
            <NTag :type="draft.extraFilterEnabled ? 'success' : 'default'" round>
              {{ draft.extraFilterEnabled ? "Enabled" : "Disabled" }}
            </NTag>
          </div>
          <ScGlobalFilterBar
            class="extra-filter-editor"
            :filter="extraFilter"
            :distinct-values="extraFilterDistinctValues"
            :numeric-ranges="extraFilterNumericRanges"
            :numeric-range-loading="extraFilterNumericRangeLoading"
            :numeric-range-errors="extraFilterNumericRangeErrors"
            show-reclassify-columns
            :reset-key="extraFilterResetKey"
            @update:filter="updateExtraFilter"
            @search-options="emit('search-extra-filter-options', $event)"
            @request-range="emit('request-extra-filter-range', $event)"
          />
          <div v-if="!draft.extraFilterEnabled" class="global-filter-actions">
            <NButton type="primary" secondary @click="setRuleEnabled('extra', true)">
              Enable for sampling
            </NButton>
          </div>
        </NCard>
      </NTabPane>

      <NTabPane v-if="hasAfterSamplingTab" name="after" tab="After sampling">
        <slot name="after-sampling" />
      </NTabPane>
    </NTabs>

    <NAlert v-if="configurationError" type="error" :show-icon="false" class="form-error">
      {{ configurationError }}
    </NAlert>

    <template #footer>
      <div class="modal-footer">
        <NText depth="3">
          {{
            loading
              ? "Resolving candidate scope…"
              : `${finalEstimate.toLocaleString()} samples planned`
          }}
        </NText>
        <div>
          <NButton @click="showModel = false">Cancel</NButton>
          <NButton
            type="primary"
            :loading="loading"
            :disabled="availableCount === 0 || !!configurationError || confirmDisabled"
            @click="handleConfirm"
          >
            Apply sampling
          </NButton>
        </div>
      </div>
    </template>
  </NModal>

  <NModal
    v-model:show="manageRulesVisible"
    preset="card"
    title="Manage sampling rules"
    :bordered="false"
    :style="manageModalStyle"
    data-testid="manage-sampling-rules-modal"
  >
    <NText depth="3">Move rules between lists to enable or disable pipeline stages.</NText>
    <div class="dual-list">
      <section class="rule-list-panel">
        <header>
          <strong>Disabled</strong><NTag size="small">{{ disabledRules.length }}</NTag>
        </header>
        <div class="rule-list" role="listbox" aria-label="Disabled sampling rules">
          <button
            v-for="item in disabledRules"
            :key="item.id"
            type="button"
            role="option"
            class="rule-list-item"
            :class="{ selected: selectedDisabledRule === item.id }"
            :aria-selected="selectedDisabledRule === item.id"
            @click="selectedDisabledRule = item.id"
            @dblclick="setRuleEnabled(item.id, true)"
          >
            <span>{{ item.order }}</span>
            <div>
              <strong>{{ item.title }}</strong
              ><small>{{ item.description }}</small>
            </div>
          </button>
          <div v-if="disabledRules.length === 0" class="empty-rules">All rules enabled.</div>
        </div>
      </section>
      <div class="transfer-controls" aria-label="Sampling rule transfer controls">
        <NButton
          circle
          type="primary"
          aria-label="Enable selected rule"
          :disabled="selectedDisabledRule === null"
          @click="moveSelectedRule(true)"
          >→</NButton
        >
        <NButton
          circle
          aria-label="Disable selected rule"
          :disabled="selectedEnabledRule === null"
          @click="moveSelectedRule(false)"
          >←</NButton
        >
      </div>
      <section class="rule-list-panel">
        <header>
          <strong>Enabled</strong><NTag size="small" type="success">{{ enabledRules.length }}</NTag>
        </header>
        <div class="rule-list" role="listbox" aria-label="Enabled sampling rules">
          <button
            v-for="item in enabledRules"
            :key="item.id"
            type="button"
            role="option"
            class="rule-list-item"
            :class="{ selected: selectedEnabledRule === item.id }"
            :aria-selected="selectedEnabledRule === item.id"
            @click="selectedEnabledRule = item.id"
            @dblclick="setRuleEnabled(item.id, false)"
          >
            <span>{{ item.order }}</span>
            <div>
              <strong>{{ item.title }}</strong
              ><small>{{ item.description }}</small>
            </div>
          </button>
          <div v-if="enabledRules.length === 0" class="empty-rules">No rules enabled.</div>
        </div>
      </section>
    </div>
    <NAlert type="info" :show-icon="false">
      Others applies the configured rule to every group value not listed explicitly.
    </NAlert>
    <template #footer>
      <div class="modal-footer">
        <span />
        <NButton type="primary" @click="manageRulesVisible = false">Done</NButton>
      </div>
    </template>
  </NModal>

  <NModal
    v-model:show="ruleConfigVisible"
    preset="card"
    :title="editingRuleItem ? `Configure ${editingRuleItem.title}` : 'Configure rule'"
    :bordered="false"
    :style="ruleModalStyle"
  >
    <div v-if="editingRule === 'conditional'" class="rule-config-panel">
      <NText depth="3">Rows outside this condition remain eligible.</NText>
      <div class="condition-grid">
        <NSelect
          v-model:value="draft.conditional.field"
          :options="SC_SAMPLING_GROUP_FIELDS"
          aria-label="Conditional field"
        />
        <NSpin :show="conditionalGroupsLoading">
          <NSelect
            v-model:value="draft.conditional.value"
            :options="
              conditionalGroups.map((group) => ({
                label: displayGroupValue(draft.conditional.field, group.value),
                value: group.value,
              }))
            "
            placeholder="Choose value"
            aria-label="Conditional value"
          />
        </NSpin>
        <NInputNumber
          v-model:value="draft.conditional.limit"
          :min="0"
          :precision="0"
          aria-label="Conditional maximum"
        >
          <template #suffix>max</template>
        </NInputNumber>
      </div>
    </div>

    <div v-else-if="editingRule === 'quota'" class="rule-config-panel">
      <div class="group-config-toolbar">
        <NSelect
          v-model:value="draft.group.field"
          :options="SC_SAMPLING_GROUP_FIELDS"
          aria-label="Group field"
        />
        <NRadioGroup v-model:value="draft.group.unit" @update:value="handleGroupModeChange">
          <NRadioButton value="count">Count</NRadioButton>
          <NRadioButton value="ratio">Sample ratio</NRadioButton>
        </NRadioGroup>
        <NSelect
          v-if="draft.group.unit === 'ratio'"
          v-model:value="draft.group.rounding"
          :options="[
            { label: 'Nearest', value: 'nearest' },
            { label: 'Floor', value: 'floor' },
            { label: 'Ceil', value: 'ceil' },
          ]"
          aria-label="Sample ratio rounding"
        />
      </div>

      <NAlert v-if="draft.group.unit === 'ratio'" type="info" :show-icon="false">
        Sample ratio is applied to each group's own eligible population: 2% of 1,000 selects 20.
      </NAlert>

      <NSpin :show="groupPopulationsLoading">
        <div class="group-table">
          <div class="group-table-head">
            <span>Group</span><span>Eligible</span><span>Rule value</span>
          </div>
          <div
            v-for="(population, index) in groupPopulations"
            :key="population.value"
            class="group-table-row"
          >
            <strong>{{ displayGroupValue(draft.group.field, population.value) }}</strong>
            <span>{{ population.count.toLocaleString() }}</span>
            <NInputNumber
              v-model:value="draft.group.targets[index]!.amount"
              :min="0"
              :max="draft.group.unit === 'ratio' ? 100 : undefined"
              :precision="draft.group.unit === 'ratio' ? 2 : 0"
              :aria-label="`${population.value} sampling target`"
            >
              <template v-if="draft.group.unit === 'ratio'" #suffix>%</template>
            </NInputNumber>
          </div>
          <div class="group-table-row group-table-others">
            <strong>Others</strong>
            <span>All other values</span>
            <NInputNumber
              v-model:value="draft.group.othersAmount"
              :min="0"
              :max="draft.group.unit === 'ratio' ? 100 : undefined"
              :precision="draft.group.unit === 'ratio' ? 2 : 0"
              aria-label="Others sampling target"
            >
              <template v-if="draft.group.unit === 'ratio'" #suffix>%</template>
            </NInputNumber>
          </div>
          <div v-if="groupPopulations.length === 0" class="empty-rules">
            No groups in this candidate scope.
          </div>
        </div>
      </NSpin>
    </div>

    <template #footer>
      <div class="modal-footer">
        <NText v-if="configurationError" type="error">{{ configurationError }}</NText>
        <NButton type="primary" @click="ruleConfigVisible = false">Done</NButton>
      </div>
    </template>
  </NModal>
</template>

<style scoped>
.scope-heading,
.rules-heading,
.global-filter-heading,
.modal-footer,
.rule-list-panel header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.scope-heading small,
.rules-heading small,
.global-filter-heading small,
.rule-copy small,
.rule-list-item small {
  color: var(--cv-text-secondary, #737373);
  font-size: 11px;
}

.scope-card,
.global-filter-card {
  background: color-mix(in srgb, var(--cv-card-bg, #fff) 94%, var(--cv-primary, #4c80f0));
}

.scope-heading strong,
.scope-heading small,
.rules-heading strong,
.rules-heading small,
.global-filter-heading strong,
.global-filter-heading small {
  display: block;
}

.scope-options {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 22px;
  margin-top: 12px;
}

.rules-heading {
  margin: 18px 0 10px;
}

.enabled-rule-list,
.rule-list,
.group-table,
.global-condition-list {
  overflow: hidden;
  border: 1px solid var(--cv-border, #e2e2e2);
  border-radius: 11px;
}

.enabled-rule-item {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) minmax(150px, 190px) auto;
  gap: 14px;
  align-items: center;
  min-height: 78px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--cv-divider, #ededed);
}

.enabled-rule-item:last-child {
  border-bottom: 0;
}

.rule-copy,
.rule-list-item {
  display: grid;
  grid-template-columns: 36px 1fr;
  gap: 8px;
  width: 100%;
  padding: 0;
  color: inherit;
  text-align: left;
  background: transparent;
  border: 0;
  cursor: pointer;
}

.rule-copy > span,
.rule-list-item > span {
  color: var(--cv-primary, #4c80f0);
  font-size: 10px;
  font-weight: 700;
}

.rule-copy strong,
.rule-copy small,
.rule-list-item strong,
.rule-list-item small {
  display: block;
}

.rule-copy small,
.rule-list-item small {
  margin-top: 3px;
  line-height: 1.35;
}

.rule-copy-static {
  cursor: default;
}

.inline-control label {
  display: block;
  margin-bottom: 5px;
  font-weight: 600;
}

.empty-rules {
  padding: 18px;
  color: var(--cv-text-secondary, #777);
  font-size: 12px;
  text-align: center;
}

.global-filter-card {
  min-height: 270px;
}

.global-filter-heading {
  align-items: flex-start;
  margin-bottom: 16px;
}

.global-filter-heading small {
  max-width: 620px;
  margin-top: 4px;
  line-height: 1.5;
}

.global-filter-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}

.extra-filter-editor {
  min-height: 220px;
}

.form-error {
  margin-top: 12px;
}

.modal-footer > div {
  display: flex;
  gap: 8px;
}

.dual-list {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 12px;
  margin: 16px 0;
}

.rule-list-panel header {
  padding: 9px 10px;
  background: color-mix(in srgb, var(--cv-primary, #4c80f0) 6%, transparent);
  border: 1px solid var(--cv-border, #e2e2e2);
  border-bottom: 0;
  border-radius: 10px 10px 0 0;
}

.rule-list-panel .rule-list {
  min-height: 270px;
  border-radius: 0 0 10px 10px;
}

.rule-list-item {
  padding: 12px 10px;
  border-bottom: 1px solid var(--cv-divider, #ededed);
}

.rule-list-item:hover,
.rule-list-item.selected {
  background: color-mix(in srgb, var(--cv-primary, #4c80f0) 10%, transparent);
}

.transfer-controls {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
}

.condition-grid,
.group-config-toolbar {
  display: grid;
  gap: 10px;
  margin: 14px 0;
}

.condition-grid {
  grid-template-columns: 1fr 1fr 150px;
}

.group-config-toolbar {
  grid-template-columns: minmax(160px, 1fr) auto minmax(150px, auto);
}

.group-table {
  margin: 14px 0 8px;
}

.group-table-head,
.group-table-row {
  display: grid;
  grid-template-columns: minmax(120px, 1fr) 110px minmax(150px, 0.8fr);
  gap: 12px;
  align-items: center;
  padding: 9px 12px;
}

.group-table-head {
  color: var(--cv-text-secondary, #777);
  font-size: 11px;
  font-weight: 600;
  background: color-mix(in srgb, var(--cv-primary, #4c80f0) 6%, transparent);
}

.group-table-row {
  border-top: 1px solid var(--cv-divider, #ededed);
}

.rule-config-panel > :deep(.n-input-number) {
  width: 100%;
}

@media (max-width: 700px) {
  .enabled-rule-item,
  .condition-grid,
  .group-config-toolbar,
  .dual-list {
    grid-template-columns: 1fr;
  }

  .transfer-controls {
    flex-direction: row;
  }
}
</style>
