<script setup lang="ts">
import { computed, ref, useSlots, watch } from "vue";
import {
  NAlert,
  NButton,
  NCard,
  NModal,
  NRadioButton,
  NRadioGroup,
  NTabPane,
  NTag,
  NTabs,
  NText,
  useMessage,
  useThemeVars,
} from "naive-ui";
import type { ScSamplingCandidateScope } from "@/features/sc/application/inspectionFilterPolicy";
import type { ScGlobalFilter } from "@/features/sc/domain/globalFilter";
import {
  cloneScSamplingProgram,
  createDefaultScSamplingRule,
  SC_REVIEW_SAMPLING_RULE_CATALOG,
  scSamplingProgramError,
  type ScSamplingClassCodesRule,
  type ScSamplingCountRule,
  type ScSamplingFinalClassDistributionRule,
  type ScSamplingGroupPopulation,
  type ScSamplingLargeDefectCountRule,
  type ScSamplingLargeDefectPercentageRule,
  type ScSamplingLimitRule,
  type ScSamplingPercentageRule,
  type ScSamplingProgram,
  type ScSamplingRule,
  type ScSamplingRuleId,
  type ScSamplingSizeRangeRule,
} from "@/features/sc/domain/samplingRules";
import { scMissingFilterOption } from "@/features/sc/domain/missingFilterValue";
import {
  scSamplingRuleEditor,
  type ScSamplingRuleEditorDescriptor,
} from "./sampling-rules/samplingRuleEditors";
import type { ScSamplingRuleEditorContext } from "./sampling-rules/types";
import ScGlobalFilterBar from "./ScGlobalFilterBar.vue";

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
    title?: string;
    distributionLabel?: string;
    showCandidateScope?: boolean;
    showExtraFilter?: boolean;
  }>(),
  {
    extraFilterDistinctValues: () => ({}),
    extraFilterNumericRanges: () => ({}),
    extraFilterNumericRangeLoading: () => ({}),
    extraFilterNumericRangeErrors: () => ({}),
    confirmDisabled: false,
    title: "Annotation Sampling",
    distributionLabel: "Final Class",
    showCandidateScope: true,
    showExtraFilter: true,
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

const message = useMessage();
const themeVars = useThemeVars();
const slots = useSlots();
const draft = ref(cloneScSamplingProgram(props.program));
const activeTab = ref<"rules" | "extra" | "after">("rules");
const catalogVisible = ref(false);
const configVisible = ref(false);
const editingRuleId = ref<ScSamplingRuleId | null>(null);
const classCodeOptions = ref<Array<{ label: string; value: number }>>([]);
const finalClassOptions = ref<Array<{ label: string; value: string }>>([]);
const groupLoading = ref(false);
let loadVersion = 0;

const surfaceStyle = computed(() => ({
  "--cv-card-bg": themeVars.value.cardColor,
  "--cv-text-secondary": themeVars.value.textColor3,
  "--cv-border": themeVars.value.borderColor,
  "--cv-divider": themeVars.value.dividerColor,
  "--cv-hover": themeVars.value.hoverColor,
  "--cv-primary": themeVars.value.primaryColor,
}));
const reviewModalStyle = computed(() => ({
  ...surfaceStyle.value,
  width: "min(1040px, calc(100vw - 32px))",
  maxHeight: "calc(100vh - 32px)",
  overflow: "auto",
}));
const catalogModalStyle = computed(() => ({
  ...surfaceStyle.value,
  width: "min(980px, calc(100vw - 32px))",
  maxHeight: "calc(100vh - 32px)",
  overflow: "auto",
}));
const configModalStyle = computed(() => ({
  ...surfaceStyle.value,
  width: "min(720px, calc(100vw - 32px))",
  maxHeight: "calc(100vh - 32px)",
  overflow: "auto",
}));

const showModel = computed({
  get: () => props.show,
  set: (show: boolean) => emit("update:show", show),
});
const scopeModel = computed({
  get: () => props.scope,
  set: (scope: ScSamplingCandidateScope) => emit("update:scope", scope),
});
const catalogItems = computed(() =>
  SC_REVIEW_SAMPLING_RULE_CATALOG.map((item) =>
    item.id === "final_class_distribution"
      ? {
          ...item,
          title: `${props.distributionLabel} distribution`,
          description: `Split a total N by ${props.distributionLabel} percentages, then draw randomly.`,
        }
      : item,
  ),
);
const enabledRules = computed(() =>
  draft.value.rules.flatMap((rule, index) => {
    const item = catalogItems.value.find((candidate) => candidate.id === rule.type);
    return item ? [{ item, rule, index }] : [];
  }),
);
const enabledIds = computed(() => new Set(draft.value.rules.map((rule) => rule.type)));
const editingRule = computed(
  () => draft.value.rules.find((rule) => rule.type === editingRuleId.value) ?? null,
);
const editingDescriptor = computed(
  () => catalogItems.value.find((item) => item.id === editingRuleId.value) ?? null,
);
const editingEditor = computed<ScSamplingRuleEditorDescriptor | null>(() =>
  editingRuleId.value ? scSamplingRuleEditor(editingRuleId.value) : null,
);
const configTitle = computed(() =>
  editingDescriptor.value ? `Configure ${editingDescriptor.value.title}` : "Configure rule",
);
const editorContext = computed<ScSamplingRuleEditorContext>(() => ({
  classCodeOptions: classCodeOptions.value,
  finalClassOptions: finalClassOptions.value,
  distributionLabel: props.distributionLabel,
  loading: groupLoading.value,
}));
const configurationError = computed(() => scSamplingProgramError(draft.value));
const hasAfterSamplingTab = computed(() => Boolean(slots["after-sampling"]));

function isPercentageRule(
  rule: ScSamplingRule,
): rule is ScSamplingPercentageRule<
  "cluster_percentage" | "repeater_percentage" | "random_percentage"
> {
  return ["cluster_percentage", "repeater_percentage", "random_percentage"].includes(rule.type);
}

function isCountRule(
  rule: ScSamplingRule,
): rule is ScSamplingCountRule<"cluster_count" | "repeater_count" | "random_count"> {
  return ["cluster_count", "repeater_count", "random_count"].includes(rule.type);
}

function isLimitRule(
  rule: ScSamplingRule,
): rule is ScSamplingLimitRule<
  "per_die_limit" | "per_cluster_limit" | "per_repeater_limit" | "per_wafer_limit"
> {
  return ["per_die_limit", "per_cluster_limit", "per_repeater_limit", "per_wafer_limit"].includes(
    rule.type,
  );
}

function isClassCodesRule(
  rule: ScSamplingRule,
): rule is ScSamplingClassCodesRule<"exclude_class_codes" | "include_class_codes"> {
  return rule.type === "exclude_class_codes" || rule.type === "include_class_codes";
}

function isSizeRangeRule(rule: ScSamplingRule): rule is ScSamplingSizeRangeRule {
  return rule.type === "size_range";
}

function isLargePercentageRule(rule: ScSamplingRule): rule is ScSamplingLargeDefectPercentageRule {
  return rule.type === "large_defect_percentage";
}

function isLargeCountRule(rule: ScSamplingRule): rule is ScSamplingLargeDefectCountRule {
  return rule.type === "large_defect_count";
}

function isFinalDistributionRule(
  rule: ScSamplingRule,
): rule is ScSamplingFinalClassDistributionRule {
  return rule.type === "final_class_distribution";
}

function ruleSummary(rule: ScSamplingRule): string {
  if (isPercentageRule(rule)) return `${rule.percentage}%`;
  if (isCountRule(rule)) return `N = ${rule.count}`;
  if (isLimitRule(rule)) return `Maximum ${rule.limit}`;
  if (isClassCodesRule(rule)) {
    return rule.classCodes.length ? rule.classCodes.join(", ") : "Class Codes required";
  }
  if (rule.type === "require_image") return "Images > 0";
  if (isSizeRangeRule(rule)) return `${rule.sizeField}: ${rule.minimum}–${rule.maximum}`;
  if (isLargePercentageRule(rule)) {
    return `${rule.sizeField} ≥ ${rule.minimum} · ${rule.percentage}%`;
  }
  if (isLargeCountRule(rule)) return `${rule.sizeField} ≥ ${rule.minimum} · N = ${rule.count}`;
  return `${rule.count} total · ${rule.targets.length} classes`;
}

function phaseLabel(phase: "eligibility" | "selector" | "cap"): string {
  if (phase === "eligibility") return "Filter step";
  if (phase === "selector") return "Take step";
  return "Limit step";
}

function stepNumber(index: number): string {
  return String(index + 1).padStart(2, "0");
}

function addRule(id: ScSamplingRuleId): void {
  if (!enabledIds.value.has(id)) draft.value.rules.push(createDefaultScSamplingRule(id));
  catalogVisible.value = false;
  openRule(id);
}

function removeRule(id: ScSamplingRuleId): void {
  draft.value.rules = draft.value.rules.filter((rule) => rule.type !== id);
  if (editingRuleId.value === id) configVisible.value = false;
}

function moveRule(index: number, offset: -1 | 1): void {
  const target = index + offset;
  if (target < 0 || target >= draft.value.rules.length) return;
  const rules = [...draft.value.rules];
  [rules[index], rules[target]] = [rules[target]!, rules[index]!];
  draft.value.rules = rules;
}

function updateRule(updatedRule: ScSamplingRule): void {
  const index = draft.value.rules.findIndex((rule) => rule.type === updatedRule.type);
  if (index >= 0) draft.value.rules[index] = updatedRule;
}

async function loadRuleOptions(rule: ScSamplingRule): Promise<void> {
  if (!isClassCodesRule(rule) && !isFinalDistributionRule(rule)) return;
  const version = ++loadVersion;
  groupLoading.value = true;
  try {
    const field = isClassCodesRule(rule) ? "class_number" : "final_class";
    const groups = await props.loadGroups(field);
    if (version !== loadVersion) return;
    if (isClassCodesRule(rule)) {
      classCodeOptions.value = groups.flatMap((group) => {
        const value = Number(group.value);
        return Number.isInteger(value) ? [{ label: group.value, value }] : [];
      });
      return;
    }
    finalClassOptions.value = groups.map((group) => ({
      label:
        scMissingFilterOption("final_class")?.value === group.value ? "Unclassified" : group.value,
      value: group.value,
    }));
    if (rule.targets.length === 0 && groups.length > 0) {
      const base = Math.floor((100 / groups.length) * 100) / 100;
      rule.targets = groups.map((group, index) => ({
        value: group.value,
        percentage: index === groups.length - 1 ? 100 - base * (groups.length - 1) : base,
      }));
    }
  } catch (error) {
    message.error(error instanceof Error ? error.message : "Failed to load rule values");
  } finally {
    if (version === loadVersion) groupLoading.value = false;
  }
}

function openRule(id: ScSamplingRuleId): void {
  editingRuleId.value = id;
  const rule = draft.value.rules.find((candidate) => candidate.type === id);
  if (!rule || scSamplingRuleEditor(id).placement === "inline") return;
  configVisible.value = true;
  void loadRuleOptions(rule);
}

function handleScopeChange(): void {
  emit("scope-change");
}

function updateExtraFilter(filter: ScGlobalFilter): void {
  emit("update:extra-filter", filter);
  handleScopeChange();
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
  },
  { immediate: true },
);

watch(draft, (program) => emit("update:program", cloneScSamplingProgram(program)), { deep: true });
</script>

<template>
  <NModal
    v-model:show="showModel"
    preset="card"
    :title="title"
    :aria-label="title"
    :bordered="false"
    :style="reviewModalStyle"
    data-testid="review-sampling-modal"
  >
    <NTabs v-model:value="activeTab" type="line" animated>
      <NTabPane name="rules" tab="Sampling rules">
        <NCard v-if="showCandidateScope" size="small" :bordered="false" class="scope-card">
          <div class="section-heading">
            <div>
              <strong>Candidate scope</strong>
              <small>Rules operate on one explicit workbench scope.</small>
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

        <div class="section-heading rules-heading">
          <div>
            <strong>Active pipeline</strong>
            <small>Runs from top to bottom. Every step receives the previous step's output.</small>
          </div>
          <NButton secondary type="primary" @click="catalogVisible = true">
            Add sampling rule
          </NButton>
        </div>

        <div class="active-rules">
          <article
            v-for="{ item, rule, index } in enabledRules"
            :key="item.id"
            class="active-rule"
            :data-testid="`sampling-rule-${item.id}`"
          >
            <div class="rule-order-control">
              <span class="rule-order">{{ stepNumber(index) }}</span>
              <div class="rule-move-actions">
                <NButton
                  size="tiny"
                  text
                  :disabled="index === 0"
                  :aria-label="`Move ${item.title} up`"
                  :data-testid="`move-sampling-rule-${item.id}-up`"
                  @click="moveRule(index, -1)"
                >
                  ↑
                </NButton>
                <NButton
                  size="tiny"
                  text
                  :disabled="index === enabledRules.length - 1"
                  :aria-label="`Move ${item.title} down`"
                  :data-testid="`move-sampling-rule-${item.id}-down`"
                  @click="moveRule(index, 1)"
                >
                  ↓
                </NButton>
              </div>
            </div>
            <div class="rule-copy">
              <div class="rule-title-line">
                <strong>{{ item.title }}</strong>
                <NTag size="small" :bordered="false">{{ phaseLabel(item.phase) }}</NTag>
              </div>
              <small>{{ item.description }}</small>
            </div>
            <component
              :is="scSamplingRuleEditor(rule.type).component"
              v-if="scSamplingRuleEditor(rule.type).placement === 'inline'"
              class="rule-inline-editor"
              :rule="rule"
              :context="editorContext"
              compact
              @update:rule="updateRule"
            />
            <NText v-else depth="3" class="rule-summary">{{ ruleSummary(rule) }}</NText>
            <div class="rule-actions">
              <NButton
                v-if="scSamplingRuleEditor(rule.type).placement === 'modal'"
                size="small"
                @click="openRule(rule.type)"
              >
                Edit
              </NButton>
              <NButton size="small" quaternary type="error" @click="removeRule(rule.type)">
                Remove
              </NButton>
            </div>
          </article>
          <div v-if="enabledRules.length === 0" class="empty-state">
            No rules enabled. Add a selector such as “All defects by count”.
          </div>
        </div>
      </NTabPane>

      <NTabPane v-if="showExtraFilter" name="extra" tab="Extra filter">
        <NCard :bordered="false" class="extra-filter-card">
          <div class="section-heading">
            <div>
              <strong>Extra filter</strong>
              <small>Apply the workbench filter before the 17 sampling rules.</small>
            </div>
            <NButton
              size="small"
              :type="draft.extraFilterEnabled ? 'primary' : 'default'"
              @click="draft.extraFilterEnabled = !draft.extraFilterEnabled"
            >
              {{ draft.extraFilterEnabled ? "Enabled" : "Disabled" }}
            </NButton>
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
          {{ enabledRules.length }} rules · {{ availableCount.toLocaleString() }} candidates
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
    v-model:show="catalogVisible"
    preset="card"
    title="Add sampling rule"
    aria-label="Add sampling rule"
    :bordered="false"
    :style="catalogModalStyle"
    data-testid="sampling-rule-catalog"
  >
    <NAlert type="info" :show-icon="false">
      New rules are appended to the pipeline. Reorder active rules to control which rows each next
      step receives.
    </NAlert>
    <div class="catalog-grid">
      <article v-for="item in catalogItems" :key="item.id" class="catalog-item">
        <div class="catalog-order">{{ item.order }}</div>
        <div>
          <div class="rule-title-line">
            <strong>{{ item.title }}</strong>
            <NTag size="small" :bordered="false">{{ phaseLabel(item.phase) }}</NTag>
          </div>
          <small>{{ item.description }}</small>
        </div>
        <NButton
          size="small"
          :disabled="enabledIds.has(item.id)"
          :data-testid="`add-sampling-rule-${item.id}`"
          @click="addRule(item.id)"
        >
          {{ enabledIds.has(item.id) ? "Enabled" : "Add" }}
        </NButton>
      </article>
    </div>
  </NModal>

  <NModal
    v-model:show="configVisible"
    preset="card"
    :title="configTitle"
    :aria-label="configTitle"
    :bordered="false"
    :style="configModalStyle"
    data-testid="sampling-rule-config"
  >
    <component
      :is="editingEditor.component"
      v-if="editingRule && editingEditor"
      :rule="editingRule"
      :context="editorContext"
      @update:rule="updateRule"
    />
    <template #footer>
      <div class="modal-footer">
        <NText v-if="configurationError" type="error">{{ configurationError }}</NText>
        <NButton type="primary" @click="configVisible = false">Done</NButton>
      </div>
    </template>
  </NModal>
</template>

<style scoped>
.section-heading,
.modal-footer,
.rule-title-line,
.rule-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.section-heading strong,
.section-heading small,
.rule-copy small {
  display: block;
}

.section-heading small,
.rule-copy small,
.catalog-item small {
  margin-top: 3px;
  color: var(--cv-text-secondary, #737373);
  font-size: 12px;
  line-height: 1.4;
}

.scope-card,
.extra-filter-card {
  background: var(--cv-card-bg, #fff);
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

.active-rules,
.catalog-grid {
  overflow: hidden;
  border: 1px solid var(--cv-border, #e2e2e2);
  border-radius: 10px;
}

.active-rule {
  display: grid;
  grid-template-columns: 62px minmax(260px, 1fr) minmax(130px, auto) auto;
  gap: 12px;
  align-items: center;
  min-height: 76px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--cv-divider, #ededed);
}

.active-rule:last-child,
.catalog-item:last-child {
  border-bottom: 0;
}

.rule-order,
.catalog-order {
  color: var(--cv-primary, #4c80f0);
  font-size: 11px;
  font-weight: 700;
}

.rule-order-control,
.rule-move-actions {
  display: flex;
  align-items: center;
}

.rule-order-control {
  gap: 7px;
}

.rule-move-actions {
  flex-direction: column;
  line-height: 1;
}

.rule-title-line {
  justify-content: flex-start;
}

.rule-summary {
  text-align: right;
}

.rule-inline-editor {
  justify-self: end;
}

.empty-state {
  padding: 20px;
  color: var(--cv-text-secondary, #737373);
  text-align: center;
}

.extra-filter-card {
  min-height: 300px;
}

.extra-filter-editor {
  min-height: 220px;
  margin-top: 16px;
}

.form-error {
  margin-top: 12px;
}

.modal-footer > div {
  display: flex;
  gap: 8px;
}

.catalog-grid {
  margin-top: 14px;
}

.catalog-item {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  min-height: 70px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--cv-divider, #ededed);
}

.catalog-item:hover,
.active-rule:hover {
  background: var(--cv-hover, #f5f5f5);
}

@media (max-width: 760px) {
  .active-rule,
  .catalog-item {
    grid-template-columns: 1fr;
  }

  .rule-summary,
  .rule-inline-editor {
    justify-self: start;
    text-align: left;
  }
}
</style>
