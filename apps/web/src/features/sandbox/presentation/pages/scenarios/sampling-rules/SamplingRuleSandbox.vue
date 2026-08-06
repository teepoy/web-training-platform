<script setup lang="ts">
import { computed, ref } from "vue";
import {
  NAlert,
  NButton,
  NCard,
  NDivider,
  NInput,
  NInputNumber,
  NModal,
  NRadioButton,
  NRadioGroup,
  NSelect,
  NTabPane,
  NTag,
  NTabs,
  useMessage,
} from "naive-ui";

type GroupRuleKind = "quota" | "rate";
type QuotaUnit = "count" | "ratio";
type GlobalFilterMatch = "all" | "any";
type GlobalFilterField = "metadata.confidence" | "metadata.defect_code";
type GlobalFilterOperator = "gte" | "lte" | "eq" | "neq";

interface PopulationGroup {
  key: string;
  label: string;
  count: number;
  filterRate: number;
  color: string;
}

interface PreviewGroup extends PopulationGroup {
  eligible: number;
  selected: number;
}

interface RuleCatalogItem {
  id: "global" | "conditional" | "quota" | "rate" | "total";
  order: string;
  title: string;
  subtitle: string;
  description: string;
}

type RuleId = RuleCatalogItem["id"];

interface GlobalFilterCondition {
  id: number;
  field: GlobalFilterField;
  operator: GlobalFilterOperator;
  value: string;
}

const groups: PopulationGroup[] = [
  {
    key: "scratch",
    label: "Scratch",
    count: 1280,
    filterRate: 0.72,
    color: "#2f7658",
  },
  {
    key: "particle",
    label: "Particle",
    count: 760,
    filterRate: 0.64,
    color: "#5b9c7c",
  },
  {
    key: "residue",
    label: "Residue",
    count: 310,
    filterRate: 0.58,
    color: "#d49a51",
  },
  {
    key: "unknown",
    label: "Unknown",
    count: 150,
    filterRate: 0.46,
    color: "#87928c",
  },
];

const catalog: RuleCatalogItem[] = [
  {
    id: "global",
    order: "01",
    title: "Global filter",
    subtitle: "全局筛选",
    description: "先收窄所有后续规则的候选池。",
  },
  {
    id: "conditional",
    order: "02",
    title: "Conditional limit",
    subtitle: "条件总量限制",
    description: "只限制命中条件的子集，其他样本保留。",
  },
  {
    id: "quota",
    order: "03A",
    title: "Group quota",
    subtitle: "按组挑选总量 / 构成比例",
    description: "控制最终样本中每个组的数量或占比。",
  },
  {
    id: "rate",
    order: "03B",
    title: "Group sampling rate",
    subtitle: "分组挑选比例",
    description: "按每个组自身候选量独立抽取一定比例。",
  },
  {
    id: "total",
    order: "04",
    title: "Total limit",
    subtitle: "总量限制",
    description: "最终结果上限；不足时不隐式补样。",
  },
];

const globalFilterFieldOptions = [
  { label: "Confidence", value: "metadata.confidence" },
  { label: "Defect code", value: "metadata.defect_code" },
];

const confidenceOperatorOptions = [
  { label: "≥", value: "gte" },
  { label: "≤", value: "lte" },
];

const categoryOperatorOptions = [
  { label: "=", value: "eq" },
  { label: "≠", value: "neq" },
];

const message = useMessage();
const globalEnabled = ref(true);
const globalFilterMatch = ref<GlobalFilterMatch>("all");
const globalFilters = ref<GlobalFilterCondition[]>([
  { id: 1, field: "metadata.confidence", operator: "gte", value: "0.65" },
]);
let nextGlobalFilterId = 2;
const conditionalEnabled = ref(true);
const conditionalGroup = ref("unknown");
const conditionalLimit = ref(45);
const groupEnabled = ref(true);
const groupRuleKind = ref<GroupRuleKind>("quota");
const quotaUnit = ref<QuotaUnit>("ratio");
const totalEnabled = ref(true);
const totalLimit = ref(200);
const seed = ref(20260731);
const runVersion = ref(1);
const rulesModalOpen = ref(false);
const ruleConfigModalOpen = ref(false);
const editingRule = ref<RuleId | null>(null);
const selectedDisabledRule = ref<RuleId | null>(null);
const selectedEnabledRule = ref<RuleId | null>(null);
const activeConfigurationTab = ref<"rules" | "global">("rules");
const groupCounts = ref<Record<string, number>>({
  scratch: 80,
  particle: 60,
  residue: 40,
  unknown: 20,
});
const groupRatios = ref<Record<string, number>>({
  scratch: 40,
  particle: 30,
  residue: 20,
  unknown: 10,
});
const groupRates = ref<Record<string, number>>({
  scratch: 10,
  particle: 15,
  residue: 25,
  unknown: 40,
});

const baseTotal = computed(() => groups.reduce((sum, group) => sum + group.count, 0));

function globalConditionRate(group: PopulationGroup, condition: GlobalFilterCondition): number {
  if (condition.field === "metadata.defect_code") {
    const matches = group.key === condition.value.trim().toLowerCase();
    return condition.operator === "neq" ? Number(!matches) : Number(matches);
  }

  const threshold = Number(condition.value);
  if (!Number.isFinite(threshold)) return 0;
  const greaterThanRate = Math.min(
    Math.max(group.filterRate + (0.65 - Math.min(Math.max(threshold, 0), 1)) * 0.8, 0),
    1,
  );
  return condition.operator === "lte" ? 1 - greaterThanRate : greaterThanRate;
}

function combinedGlobalFilterRate(group: PopulationGroup): number {
  const rates = globalFilters.value.map((condition) => globalConditionRate(group, condition));
  if (rates.length === 0) return 1;
  if (globalFilterMatch.value === "any") {
    return 1 - rates.reduce((missRate, rate) => missRate * (1 - rate), 1);
  }
  return rates.reduce((combined, rate) => combined * rate, 1);
}

const afterGlobal = computed(() =>
  groups.map((group) => {
    return {
      ...group,
      eligible: globalEnabled.value
        ? Math.floor(group.count * combinedGlobalFilterRate(group))
        : group.count,
    };
  }),
);
const globalTotal = computed(() =>
  afterGlobal.value.reduce((sum, group) => sum + group.eligible, 0),
);
const afterConditional = computed(() =>
  afterGlobal.value.map((group) => ({
    ...group,
    eligible:
      conditionalEnabled.value && group.key === conditionalGroup.value
        ? Math.min(group.eligible, conditionalLimit.value ?? 0)
        : group.eligible,
  })),
);
const conditionalTotal = computed(() =>
  afterConditional.value.reduce((sum, group) => sum + group.eligible, 0),
);
const ratioTotal = computed(() =>
  groups.reduce((sum, group) => sum + (groupRatios.value[group.key] ?? 0), 0),
);
const totalLimitValue = computed(() =>
  totalEnabled.value ? Math.max(totalLimit.value ?? 0, 0) : conditionalTotal.value,
);

function largestRemainder(values: number[], total: number): number[] {
  const ideals = values.map((value) => (value / 100) * total);
  const result = ideals.map(Math.floor);
  let remaining = total - result.reduce((sum, value) => sum + value, 0);
  const ranked = ideals
    .map((ideal, index) => ({ index, remainder: ideal - Math.floor(ideal) }))
    .sort((left, right) => right.remainder - left.remainder || left.index - right.index);
  for (const { index } of ranked) {
    if (remaining === 0) break;
    result[index] = (result[index] ?? 0) + 1;
    remaining -= 1;
  }
  return result;
}

const groupStage = computed<PreviewGroup[]>(() => {
  const eligible = afterConditional.value;
  if (!groupEnabled.value) {
    return eligible.map((group) => ({ ...group, selected: group.eligible }));
  }
  if (groupRuleKind.value === "rate") {
    return eligible.map((group) => ({
      ...group,
      selected: Math.min(
        group.eligible,
        Math.floor((group.eligible * (groupRates.value[group.key] ?? 0)) / 100 + 0.5),
      ),
    }));
  }
  const planned =
    quotaUnit.value === "count"
      ? groups.map((group) => groupCounts.value[group.key] ?? 0)
      : largestRemainder(
          groups.map((group) => groupRatios.value[group.key] ?? 0),
          totalLimitValue.value,
        );
  return eligible.map((group, index) => ({
    ...group,
    selected: Math.min(group.eligible, planned[index] ?? 0),
  }));
});

const groupTotal = computed(() => groupStage.value.reduce((sum, group) => sum + group.selected, 0));
const finalTotal = computed(() => Math.min(groupTotal.value, totalLimitValue.value));
const ratioValid = computed(
  () =>
    groupRuleKind.value !== "quota" ||
    quotaUnit.value !== "ratio" ||
    (totalEnabled.value && ratioTotal.value === 100),
);
const globalFiltersValid = computed(
  () =>
    globalFilters.value.length > 0 &&
    globalFilters.value.every((condition) => {
      if (condition.value.trim() === "") return false;
      if (condition.field === "metadata.defect_code") {
        return condition.operator === "eq" || condition.operator === "neq";
      }
      const threshold = Number(condition.value);
      return (
        (condition.operator === "gte" || condition.operator === "lte") &&
        Number.isFinite(threshold) &&
        threshold >= 0 &&
        threshold <= 1
      );
    }),
);
const hasConfigurationError = computed(
  () =>
    (globalEnabled.value && !globalFiltersValid.value) ||
    !ratioValid.value ||
    (conditionalEnabled.value && (conditionalLimit.value ?? -1) < 0) ||
    (totalEnabled.value && (totalLimit.value ?? -1) < 0),
);

const finalGroups = computed<PreviewGroup[]>(() => {
  if (groupTotal.value <= finalTotal.value) return groupStage.value;
  const values = groupStage.value.map(
    (group) => (group.selected / Math.max(groupTotal.value, 1)) * 100,
  );
  const capped = largestRemainder(values, finalTotal.value);
  return groupStage.value.map((group, index) => ({
    ...group,
    selected: Math.min(group.selected, capped[index] ?? 0),
  }));
});
const maxSelected = computed(() =>
  Math.max(...finalGroups.value.map((group) => group.selected), 1),
);

const activeRuleCount = computed(
  () =>
    Number(globalEnabled.value) +
    Number(conditionalEnabled.value) +
    Number(groupEnabled.value) +
    Number(totalEnabled.value),
);

const stageCounts = computed(() => [
  { label: "Input", value: baseTotal.value },
  { label: "Global", value: globalTotal.value },
  { label: "Conditional", value: conditionalTotal.value },
  { label: "Group", value: groupTotal.value },
  { label: "Final", value: finalTotal.value },
]);

const rulePayload = computed(() => {
  const rules: Array<Record<string, unknown>> = [];
  if (globalEnabled.value) {
    rules.push({
      type: "global_filter",
      where: {
        match: globalFilterMatch.value,
        conditions: globalFilters.value.map((condition) => ({
          field: condition.field,
          operator: condition.operator,
          value:
            condition.field === "metadata.confidence" ? Number(condition.value) : condition.value,
        })),
      },
    });
  }
  if (conditionalEnabled.value) {
    rules.push({
      type: "conditional_limit",
      where: {
        match: "all",
        conditions: [
          {
            field: "metadata.defect_code",
            operator: "eq",
            value: conditionalGroup.value,
          },
        ],
      },
      limit: conditionalLimit.value,
    });
  }
  if (groupEnabled.value && groupRuleKind.value === "quota") {
    rules.push({
      type: "group_quota",
      group_by: ["metadata.defect_code"],
      unit: quotaUnit.value,
      targets: groups.map((group) => ({
        group: [group.key],
        amount:
          quotaUnit.value === "count"
            ? groupCounts.value[group.key]
            : (groupRatios.value[group.key] ?? 0) / 100,
      })),
      shortfall: "take_available",
      unlisted: "exclude",
    });
  }
  if (groupEnabled.value && groupRuleKind.value === "rate") {
    rules.push({
      type: "group_sampling_rate",
      group_by: ["metadata.defect_code"],
      rates: groups.map((group) => ({
        group: [group.key],
        ratio: (groupRates.value[group.key] ?? 0) / 100,
      })),
      rounding: "nearest",
      unlisted: "exclude",
    });
  }
  if (totalEnabled.value) {
    rules.push({ type: "total_limit", limit: totalLimit.value });
  }
  return { seed: seed.value, rules };
});

function ruleIsActive(id: RuleCatalogItem["id"]): boolean {
  if (id === "global") return globalEnabled.value;
  if (id === "conditional") return conditionalEnabled.value;
  if (id === "total") return totalEnabled.value;
  return groupEnabled.value && groupRuleKind.value === id;
}

const disabledRules = computed(() => catalog.filter((rule) => !ruleIsActive(rule.id)));
const enabledRules = computed(() => catalog.filter((rule) => ruleIsActive(rule.id)));
const configurableEnabledRules = computed(() =>
  enabledRules.value.filter((rule) => rule.id !== "global"),
);
const editingRuleItem = computed(
  () => catalog.find((rule) => rule.id === editingRule.value) ?? null,
);

function globalOperatorOptions(field: GlobalFilterField) {
  return field === "metadata.confidence" ? confidenceOperatorOptions : categoryOperatorOptions;
}

function updateGlobalFilterField(condition: GlobalFilterCondition, field: string): void {
  if (field !== "metadata.confidence" && field !== "metadata.defect_code") return;
  condition.field = field;
  condition.operator = field === "metadata.confidence" ? "gte" : "eq";
  condition.value = field === "metadata.confidence" ? "0.65" : "unknown";
}

function addGlobalFilter(): void {
  globalFilters.value.push({
    id: nextGlobalFilterId,
    field: "metadata.defect_code",
    operator: "eq",
    value: "unknown",
  });
  nextGlobalFilterId += 1;
}

function removeGlobalFilter(id: number): void {
  globalFilters.value = globalFilters.value.filter((condition) => condition.id !== id);
}

function setRuleEnabled(id: RuleId, enabled: boolean): void {
  if (id === "global") globalEnabled.value = enabled;
  else if (id === "conditional") conditionalEnabled.value = enabled;
  else if (id === "total") totalEnabled.value = enabled;
  else if (enabled) {
    groupEnabled.value = true;
    groupRuleKind.value = id;
  } else if (groupEnabled.value && groupRuleKind.value === id) {
    groupEnabled.value = false;
  }

  selectedDisabledRule.value = null;
  selectedEnabledRule.value = enabled ? id : null;
  if (!enabled && editingRule.value === id) {
    editingRule.value = null;
    ruleConfigModalOpen.value = false;
  }
}

function moveSelectedRule(enabled: boolean): void {
  const ruleId = enabled ? selectedDisabledRule.value : selectedEnabledRule.value;
  if (ruleId) setRuleEnabled(ruleId, enabled);
}

function openRulesModal(): void {
  selectedDisabledRule.value = null;
  selectedEnabledRule.value = null;
  rulesModalOpen.value = true;
}

function openRuleConfiguration(id: RuleId): void {
  if (id === "global") {
    activeConfigurationTab.value = "global";
    return;
  }
  editingRule.value = id;
  ruleConfigModalOpen.value = true;
}

function runPreview(): void {
  if (hasConfigurationError.value) {
    message.error("Resolve the rule configuration errors before previewing.");
    return;
  }
  runVersion.value += 1;
  message.success(
    `${activeRuleCount.value} rules resolved ${finalTotal.value} random samples with seed ${seed.value}.`,
  );
}
</script>

<template>
  <main class="sampling-builder">
    <header class="page-header">
      <div>
        <div class="eyebrow">SAMPLING LAB · RULE PIPELINE</div>
        <h1>Sampling rule builder</h1>
        <p>Rules narrow and shape the candidate pool; random sampling still chooses the rows.</p>
      </div>
      <NButton type="primary" size="large" :disabled="hasConfigurationError" @click="runPreview">
        Run preview
      </NButton>
    </header>

    <section class="pipeline-strip">
      <template v-for="(stage, index) in stageCounts" :key="stage.label">
        <div class="pipeline-stage" :class="{ final: index === stageCounts.length - 1 }">
          <small>{{ index === 0 ? "SOURCE" : `0${index}` }}</small>
          <strong>{{ stage.value.toLocaleString() }}</strong>
          <span>{{ stage.label }}</span>
        </div>
        <span v-if="index < stageCounts.length - 1" class="pipeline-arrow">→</span>
      </template>
      <div class="random-badge">
        <span>RANDOM</span>
        <strong>seed {{ seed }}</strong>
      </div>
    </section>

    <div class="builder-grid">
      <section class="editor-column">
        <div class="section-heading">
          <div>
            <div class="section-label">ACTIVE PIPELINE</div>
            <h2>Rule configuration</h2>
          </div>
          <div class="rule-actions">
            <NTag round type="success">{{ activeRuleCount }} active</NTag>
            <NButton secondary type="primary" @click="openRulesModal"> Manage rules </NButton>
          </div>
        </div>

        <NTabs v-model:value="activeConfigurationTab" type="line" animated class="config-tabs">
          <NTabPane name="rules" tab="Enabled rules">
            <div class="enabled-rule-list">
              <article
                v-for="item in configurableEnabledRules"
                :key="item.id"
                class="enabled-rule-item"
              >
                <button
                  class="enabled-rule-main"
                  type="button"
                  :aria-label="`Configure ${item.title}`"
                  @click="openRuleConfiguration(item.id)"
                >
                  <span class="rule-index">{{ item.order.replace("A", "").replace("B", "") }}</span>
                  <span class="enabled-rule-copy">
                    <strong>{{ item.title }}</strong>
                    <small>{{ item.subtitle }}</small>
                    <em>{{ item.description }}</em>
                  </span>
                </button>

                <div class="inline-rule-control">
                  <template v-if="item.id === 'conditional'">
                    <label>Matched max</label>
                    <NInputNumber
                      v-model:value="conditionalLimit"
                      :min="0"
                      :precision="0"
                      aria-label="Conditional limit"
                    />
                  </template>
                  <template v-else-if="item.id === 'total'">
                    <label>Final max</label>
                    <NInputNumber
                      v-model:value="totalLimit"
                      :min="0"
                      :precision="0"
                      aria-label="Total limit"
                    />
                  </template>
                  <template v-else>
                    <label>Configuration</label>
                    <NTag size="small" type="success">
                      {{
                        groupRuleKind === "quota"
                          ? quotaUnit === "ratio"
                            ? `${ratioTotal}% final`
                            : `${groupTotal} planned`
                          : `${groupTotal} planned`
                      }}
                    </NTag>
                  </template>
                </div>

                <NButton
                  secondary
                  size="small"
                  :aria-label="`Open ${item.title} configuration`"
                  @click="openRuleConfiguration(item.id)"
                >
                  Edit
                </NButton>
              </article>
              <div v-if="configurableEnabledRules.length === 0" class="empty-enabled-rules">
                No configurable rules enabled. Use Manage rules to add one.
              </div>
            </div>
          </NTabPane>

          <NTabPane name="global" tab="Global filter">
            <NCard :bordered="false" class="global-filter-card">
              <div class="global-filter-header">
                <div>
                  <div class="rule-title">
                    <span class="rule-index">01</span>
                    <div><strong>Global filter</strong><small>全局筛选</small></div>
                  </div>
                  <p>Combine multiple conditions before any sampling limits are applied.</p>
                </div>
                <NTag :type="globalEnabled ? 'success' : 'default'" round>
                  {{ globalEnabled ? "Enabled" : "Disabled" }}
                </NTag>
              </div>

              <template v-if="globalEnabled">
                <div class="global-filter-toolbar">
                  <div>
                    <span>Match</span>
                    <NRadioGroup v-model:value="globalFilterMatch" size="small">
                      <NRadioButton value="all">All conditions</NRadioButton>
                      <NRadioButton value="any">Any condition</NRadioButton>
                    </NRadioGroup>
                  </div>
                  <NButton secondary type="primary" size="small" @click="addGlobalFilter">
                    + Add filter
                  </NButton>
                </div>

                <div class="global-filter-list">
                  <div
                    v-for="(condition, index) in globalFilters"
                    :key="condition.id"
                    class="global-filter-row"
                  >
                    <span class="filter-sequence">{{ String(index + 1).padStart(2, "0") }}</span>
                    <NSelect
                      :value="condition.field"
                      :options="globalFilterFieldOptions"
                      aria-label="Global filter field"
                      @update:value="(value) => updateGlobalFilterField(condition, String(value))"
                    />
                    <NSelect
                      v-model:value="condition.operator"
                      :options="globalOperatorOptions(condition.field)"
                      aria-label="Global filter operator"
                    />
                    <NInput
                      v-model:value="condition.value"
                      :placeholder="
                        condition.field === 'metadata.confidence' ? '0.00 – 1.00' : 'Defect code'
                      "
                      aria-label="Global filter value"
                    />
                    <NButton
                      quaternary
                      circle
                      aria-label="Remove global filter"
                      @click="removeGlobalFilter(condition.id)"
                    >
                      ×
                    </NButton>
                  </div>
                </div>

                <NAlert v-if="!globalFiltersValid" type="error" :show-icon="false">
                  Add at least one complete filter. Confidence values must be between 0 and 1.
                </NAlert>

                <div class="rule-foot">
                  <span>{{ globalFilters.length }} conditions · match {{ globalFilterMatch }}</span>
                  <strong
                    >{{ baseTotal.toLocaleString() }} → {{ globalTotal.toLocaleString() }}</strong
                  >
                </div>
              </template>

              <NAlert v-else type="info" :show-icon="false">
                Global filter is disabled. Enable it from Manage rules to edit its conditions.
              </NAlert>
            </NCard>
          </NTabPane>
        </NTabs>

        <NCard :bordered="false" class="seed-card">
          <div class="seed-row">
            <div>
              <strong>Random draw</strong>
              <small>规则只决定候选与配额；seed 决定具体选中哪些行。</small>
            </div>
            <NInputNumber v-model:value="seed" :precision="0" />
          </div>
        </NCard>
      </section>

      <aside class="preview-column">
        <NCard :bordered="false" class="preview-card">
          <template #header>
            <div>
              <strong>Final distribution</strong>
              <small>after all active rules</small>
            </div>
          </template>
          <div class="final-total">
            <strong>{{ finalTotal }}</strong>
            <span>random samples</span>
          </div>
          <NDivider />
          <div v-for="group in finalGroups" :key="group.key" class="distribution-row">
            <div>
              <span class="group-name"
                ><i :style="{ background: group.color }" />{{ group.label }}</span
              >
              <small>{{ group.selected }} / {{ group.eligible }}</small>
            </div>
            <div class="distribution-track">
              <span
                :style="{
                  width: `${(group.selected / maxSelected) * 100}%`,
                  background: group.color,
                }"
              />
            </div>
            <strong>{{ ((group.selected / Math.max(finalTotal, 1)) * 100).toFixed(0) }}%</strong>
          </div>
        </NCard>

        <NCard title="Rule audit" :bordered="false" class="preview-card audit-card">
          <div v-for="(stage, index) in stageCounts.slice(1)" :key="stage.label" class="audit-row">
            <span>0{{ index + 1 }}</span>
            <div>
              <strong>{{ stage.label }}</strong
              ><small>{{ stage.value }} remain</small>
            </div>
            <em>{{ index === stageCounts.length - 2 ? "FINAL" : "PASS" }}</em>
          </div>
        </NCard>

        <NCard title="Library payload" :bordered="false" class="preview-card payload-card">
          <pre>{{ JSON.stringify(rulePayload, null, 2) }}</pre>
        </NCard>
      </aside>
    </div>

    <NModal
      v-model:show="rulesModalOpen"
      preset="card"
      title="Manage sampling rules"
      class="rules-modal"
      :bordered="false"
    >
      <p class="modal-description">
        Move rules between the two lists to enable or disable them in the sampling pipeline.
      </p>

      <div class="dual-list">
        <section class="rule-list-panel">
          <header>
            <div>
              <span>DISABLED</span>
              <strong>Available rules</strong>
            </div>
            <NTag round size="small">{{ disabledRules.length }}</NTag>
          </header>
          <div class="rule-list" role="listbox" aria-label="Disabled rules">
            <button
              v-for="item in disabledRules"
              :key="item.id"
              class="rule-list-item"
              :class="{ selected: selectedDisabledRule === item.id }"
              type="button"
              role="option"
              :aria-selected="selectedDisabledRule === item.id"
              @click="selectedDisabledRule = item.id"
              @dblclick="setRuleEnabled(item.id, true)"
            >
              <span class="catalog-order">{{ item.order }}</span>
              <span class="catalog-copy">
                <strong>{{ item.title }}</strong>
                <small>{{ item.subtitle }}</small>
                <em>{{ item.description }}</em>
              </span>
            </button>
            <div v-if="disabledRules.length === 0" class="empty-list">All rules are enabled.</div>
          </div>
        </section>

        <div class="transfer-controls" aria-label="Rule transfer controls">
          <NButton
            circle
            type="primary"
            aria-label="Enable selected rule"
            :disabled="selectedDisabledRule === null"
            @click="moveSelectedRule(true)"
          >
            →
          </NButton>
          <NButton
            circle
            aria-label="Disable selected rule"
            :disabled="selectedEnabledRule === null"
            @click="moveSelectedRule(false)"
          >
            ←
          </NButton>
        </div>

        <section class="rule-list-panel enabled-panel">
          <header>
            <div>
              <span>ENABLED</span>
              <strong>Active pipeline</strong>
            </div>
            <NTag round size="small" type="success">{{ enabledRules.length }}</NTag>
          </header>
          <div class="rule-list" role="listbox" aria-label="Enabled rules">
            <button
              v-for="item in enabledRules"
              :key="item.id"
              class="rule-list-item"
              :class="{ selected: selectedEnabledRule === item.id }"
              type="button"
              role="option"
              :aria-selected="selectedEnabledRule === item.id"
              @click="selectedEnabledRule = item.id"
              @dblclick="setRuleEnabled(item.id, false)"
            >
              <span class="catalog-order">{{ item.order }}</span>
              <span class="catalog-copy">
                <strong>{{ item.title }}</strong>
                <small>{{ item.subtitle }}</small>
                <em>{{ item.description }}</em>
              </span>
            </button>
            <div v-if="enabledRules.length === 0" class="empty-list">No rules are enabled.</div>
          </div>
        </section>
      </div>

      <NAlert type="info" :show-icon="false" class="modal-note">
        03A 与 03B 是互斥的分组策略；启用其中一项会自动替换另一项。
      </NAlert>
    </NModal>

    <NModal
      v-model:show="ruleConfigModalOpen"
      preset="card"
      :title="editingRuleItem ? `Configure ${editingRuleItem.title}` : 'Configure rule'"
      class="config-modal"
      :bordered="false"
    >
      <div v-if="editingRule === 'conditional'" class="config-panel">
        <div class="rule-title config-rule-title">
          <span class="rule-index">02</span>
          <div><strong>Conditional limit</strong><small>条件总量限制</small></div>
        </div>
        <div class="condition-row">
          <NSelect
            value="metadata.defect_code"
            :options="[{ label: 'Defect code', value: 'metadata.defect_code' }]"
          />
          <NSelect value="eq" :options="[{ label: '=', value: 'eq' }]" />
          <NSelect
            v-model:value="conditionalGroup"
            :options="groups.map((group) => ({ label: group.label, value: group.key }))"
          />
          <NInputNumber v-model:value="conditionalLimit" :min="0" :precision="0">
            <template #suffix>max</template>
          </NInputNumber>
        </div>
        <div class="rule-foot">
          <span>只收紧命中组，未命中样本保留</span>
          <strong
            >{{ globalTotal.toLocaleString() }} → {{ conditionalTotal.toLocaleString() }}</strong
          >
        </div>
      </div>

      <div v-else-if="editingRule === 'quota' || editingRule === 'rate'" class="config-panel">
        <div class="rule-title config-rule-title">
          <span class="rule-index">03</span>
          <div>
            <strong>{{ groupRuleKind === "quota" ? "Group quota" : "Group sampling rate" }}</strong>
            <small>{{
              groupRuleKind === "quota" ? "按组挑选总量 / 构成比例" : "分组挑选比例"
            }}</small>
          </div>
        </div>
        <div class="group-toolbar">
          <NRadioGroup v-if="groupRuleKind === 'quota'" v-model:value="quotaUnit">
            <NRadioButton value="count">Count</NRadioButton>
            <NRadioButton value="ratio">Final ratio</NRadioButton>
          </NRadioGroup>
        </div>

        <NAlert
          v-if="groupRuleKind === 'quota' && quotaUnit === 'ratio' && !totalEnabled"
          type="error"
          :show-icon="false"
        >
          Final ratio requires a total limit to resolve absolute quotas.
        </NAlert>
        <NAlert
          v-else-if="groupRuleKind === 'quota' && quotaUnit === 'ratio' && ratioTotal !== 100"
          type="error"
          :show-icon="false"
        >
          Final composition ratios must total 100%; current total is {{ ratioTotal }}%.
        </NAlert>

        <div class="group-table">
          <div class="group-table-head">
            <span>Group</span><span>Eligible</span><span>Rule value</span><span>Planned</span>
          </div>
          <div v-for="group in groupStage" :key="group.key" class="group-table-row">
            <span class="group-name"
              ><i :style="{ background: group.color }" />{{ group.label }}</span
            >
            <span>{{ group.eligible.toLocaleString() }}</span>
            <NInputNumber
              v-if="groupRuleKind === 'quota' && quotaUnit === 'count'"
              v-model:value="groupCounts[group.key]"
              :min="0"
              :precision="0"
            />
            <NInputNumber
              v-else-if="groupRuleKind === 'quota'"
              v-model:value="groupRatios[group.key]"
              :min="0"
              :max="100"
              :precision="0"
            >
              <template #suffix>% final</template>
            </NInputNumber>
            <NInputNumber
              v-else
              v-model:value="groupRates[group.key]"
              :min="0"
              :max="100"
              :precision="0"
            >
              <template #suffix>% group</template>
            </NInputNumber>
            <strong>{{ group.selected }}</strong>
          </div>
        </div>
        <div class="rule-foot">
          <span>{{
            groupRuleKind === "quota"
              ? "控制最终构成；组不足时 take_available"
              : "每个组按自身候选量计算"
          }}</span>
          <strong
            >{{ conditionalTotal.toLocaleString() }} → {{ groupTotal.toLocaleString() }}</strong
          >
        </div>
      </div>

      <div v-else-if="editingRule === 'total'" class="config-panel">
        <div class="rule-title config-rule-title">
          <span class="rule-index">04</span>
          <div><strong>Total limit</strong><small>总量限制</small></div>
        </div>
        <div class="total-limit-row">
          <div>
            <span>Maximum final samples</span>
            <small>这是上限，不会为了凑数隐式补样。</small>
          </div>
          <NInputNumber v-model:value="totalLimit" :min="0" :precision="0" />
        </div>
        <div class="rule-foot">
          <span>最终随机收口</span>
          <strong>{{ groupTotal.toLocaleString() }} → {{ finalTotal.toLocaleString() }}</strong>
        </div>
      </div>
    </NModal>
  </main>
</template>

<style scoped>
.sampling-builder {
  min-height: 100%;
  padding: 28px;
  color: #18251f;
  background:
    radial-gradient(circle at 92% 2%, rgba(190, 218, 199, 0.52), transparent 28rem), #f3f6f2;
}

.page-header,
.section-heading,
.rule-title,
.rule-foot,
.total-limit-row,
.seed-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.page-header,
.pipeline-strip,
.builder-grid {
  max-width: 1540px;
  margin-right: auto;
  margin-left: auto;
}

.page-header {
  margin-bottom: 20px;
}

.page-header > :deep(.n-button) {
  flex-shrink: 0;
}

.eyebrow,
.section-label {
  color: #397457;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.16em;
}

h1 {
  margin: 5px 0 0;
  font-size: clamp(27px, 3vw, 38px);
  line-height: 1.12;
  letter-spacing: -0.035em;
}

.page-header p {
  margin: 8px 0 0;
  color: #64726b;
}

.pipeline-strip {
  display: flex;
  align-items: stretch;
  gap: 11px;
  padding: 13px;
  margin-bottom: 22px;
  overflow: hidden;
  background: #dfece2;
  border: 1px solid #d3e1d6;
  border-radius: 17px;
}

.pipeline-stage {
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto;
  column-gap: 9px;
  align-items: center;
  min-width: 112px;
  padding: 8px 10px;
}

.pipeline-stage small {
  grid-row: 1 / 3;
  color: #4c7b62;
  font-size: 9px;
  font-weight: 800;
}

.pipeline-stage strong {
  font-size: 17px;
  line-height: 1;
}

.pipeline-stage span {
  color: #718078;
  font-size: 10px;
}

.pipeline-stage.final {
  background: rgba(255, 255, 255, 0.68);
  border-radius: 11px;
}

.pipeline-arrow {
  align-self: center;
  color: #8ba093;
}

.random-badge {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 8px 15px;
  margin-left: auto;
  color: white;
  background: #326e52;
  border-radius: 11px;
}

.random-badge span {
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.12em;
}

.random-badge strong {
  margin-top: 2px;
  font-size: 11px;
}

.builder-grid {
  display: grid;
  grid-template-columns: minmax(560px, 1.55fr) minmax(280px, 0.72fr);
  gap: 18px;
  align-items: start;
}

.editor-column,
.preview-column {
  min-width: 0;
}

.rule-list-item {
  display: grid;
  grid-template-columns: 32px 1fr;
  gap: 10px;
  width: 100%;
  padding: 14px 12px;
  color: inherit;
  text-align: left;
  background: #fff;
  border: 0;
  border-bottom: 1px solid #e8ece8;
  cursor: pointer;
  transition: background 150ms ease;
}

.rule-list-item:last-child {
  border-bottom: 0;
}

.rule-list-item:hover {
  background: #f5f8f5;
}

.rule-list-item.selected {
  background: #e5f1e8;
  box-shadow: inset 3px 0 #397457;
}

.catalog-order {
  color: #5c8b70;
  font-size: 10px;
  font-weight: 800;
}

.catalog-copy,
.catalog-copy strong,
.catalog-copy small,
.catalog-copy em {
  display: block;
}

.catalog-copy strong {
  font-size: 13px;
}

.catalog-copy small {
  margin-top: 2px;
  color: #557264;
  font-size: 10px;
}

.catalog-copy em {
  margin-top: 6px;
  color: #7a867f;
  font-size: 10px;
  font-style: normal;
  line-height: 1.4;
}

.rule-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.config-tabs {
  margin-bottom: 14px;
}

.config-tabs :deep(.n-tabs-nav) {
  padding: 0 4px;
}

.enabled-rule-list {
  margin-bottom: 14px;
  overflow: hidden;
  background: #fff;
  border: 1px solid #dfe5df;
  border-radius: 15px;
  box-shadow: 0 9px 30px rgba(31, 52, 42, 0.045);
}

.enabled-rule-item {
  display: grid;
  grid-template-columns: minmax(250px, 1fr) minmax(150px, 190px) auto;
  gap: 16px;
  align-items: center;
  min-height: 92px;
  padding: 13px 16px;
  border-bottom: 1px solid #e9ede9;
}

.enabled-rule-item:last-child {
  border-bottom: 0;
}

.enabled-rule-main {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 6px;
  color: inherit;
  text-align: left;
  background: transparent;
  border: 0;
  border-radius: 10px;
  cursor: pointer;
}

.enabled-rule-main:hover {
  background: #f2f7f3;
}

.enabled-rule-copy,
.enabled-rule-copy strong,
.enabled-rule-copy small,
.enabled-rule-copy em {
  display: block;
}

.enabled-rule-copy strong {
  font-size: 13px;
}

.enabled-rule-copy small {
  margin-top: 2px;
  color: #557264;
  font-size: 10px;
}

.enabled-rule-copy em {
  margin-top: 5px;
  color: #7a867f;
  font-size: 10px;
  font-style: normal;
}

.inline-rule-control {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.inline-rule-control label {
  color: #78847d;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.empty-enabled-rules {
  display: grid;
  min-height: 130px;
  color: #8a958f;
  font-size: 12px;
  place-items: center;
}

.global-filter-card {
  overflow: hidden;
  border: 1px solid #dfe5df;
  border-radius: 15px;
  box-shadow: 0 9px 30px rgba(31, 52, 42, 0.045);
}

.global-filter-header,
.global-filter-toolbar,
.global-filter-toolbar > div {
  display: flex;
  align-items: center;
}

.global-filter-header,
.global-filter-toolbar {
  justify-content: space-between;
  gap: 16px;
}

.global-filter-header p {
  margin: 8px 0 0;
  color: #748078;
  font-size: 11px;
}

.global-filter-toolbar {
  padding: 14px 0;
  margin-top: 18px;
  border-top: 1px solid #e8ece8;
  border-bottom: 1px solid #e8ece8;
}

.global-filter-toolbar > div {
  gap: 10px;
}

.global-filter-toolbar span {
  color: #78847d;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.global-filter-list {
  margin: 14px 0;
  overflow: hidden;
  border: 1px solid #e4e9e4;
  border-radius: 12px;
}

.global-filter-row {
  display: grid;
  grid-template-columns: 34px minmax(150px, 1.2fr) 90px minmax(130px, 1fr) 34px;
  gap: 9px;
  align-items: center;
  padding: 10px;
  background: #fbfcfb;
  border-bottom: 1px solid #e8ece8;
}

.global-filter-row:last-child {
  border-bottom: 0;
}

.filter-sequence {
  color: #5f8d73;
  font-size: 9px;
  font-weight: 800;
}

.rules-modal {
  width: min(920px, calc(100vw - 32px));
}

.rules-modal :deep(.n-card__content) {
  max-height: calc(100vh - 140px);
  overflow-y: auto;
}

.modal-description {
  margin: -4px 0 18px;
  color: #6d7972;
  font-size: 13px;
}

.dual-list {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 52px minmax(0, 1fr);
  gap: 14px;
  align-items: stretch;
}

.rule-list-panel {
  overflow: hidden;
  background: #f8faf8;
  border: 1px solid #dfe5df;
  border-radius: 14px;
}

.rule-list-panel > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 66px;
  padding: 12px 14px;
  border-bottom: 1px solid #dfe5df;
}

.rule-list-panel > header span,
.rule-list-panel > header strong {
  display: block;
}

.rule-list-panel > header span {
  color: #879189;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.12em;
}

.rule-list-panel > header strong {
  margin-top: 3px;
  font-size: 14px;
}

.enabled-panel > header {
  background: #edf5ef;
}

.rule-list {
  min-height: 300px;
  max-height: 410px;
  overflow-y: auto;
}

.transfer-controls {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.empty-list {
  display: grid;
  min-height: 300px;
  color: #929c96;
  font-size: 12px;
  place-items: center;
}

.modal-note {
  margin-top: 16px;
  font-size: 11px;
}

.config-modal {
  width: min(780px, calc(100vw - 32px));
}

.config-modal :deep(.n-card__content) {
  max-height: calc(100vh - 160px);
  overflow-y: auto;
}

.config-panel {
  padding: 4px 2px 2px;
}

.config-rule-title {
  margin-bottom: 18px;
}

.section-heading {
  min-height: 44px;
  margin-bottom: 10px;
}

.section-heading h2 {
  margin: 3px 0 0;
  font-size: 20px;
}

.rule-card,
.seed-card,
.preview-card {
  margin-bottom: 14px;
  overflow: hidden;
  border: 1px solid #dfe5df;
  border-radius: 15px;
  box-shadow: 0 9px 30px rgba(31, 52, 42, 0.045);
}

.rule-card :deep(.n-card-header) {
  padding-bottom: 14px;
}

.rule-title {
  justify-content: flex-start;
  gap: 10px;
}

.rule-index {
  display: grid;
  width: 31px;
  height: 31px;
  color: #347052;
  font-size: 10px;
  font-weight: 800;
  background: #e3efe6;
  border-radius: 9px;
  place-items: center;
}

.rule-title strong,
.rule-title small,
.preview-card :deep(.n-card-header__main) strong,
.preview-card :deep(.n-card-header__main) small {
  display: block;
}

.rule-title strong {
  font-size: 14px;
}

.rule-title small {
  margin-top: 1px;
  color: #728078;
  font-size: 10px;
}

.condition-row {
  display: grid;
  grid-template-columns: minmax(140px, 1.4fr) minmax(70px, 0.45fr) minmax(110px, 0.9fr) minmax(
      100px,
      0.75fr
    );
  gap: 9px;
}

.condition-row > :last-child:nth-child(3) {
  grid-column: 3 / 5;
}

.rule-foot {
  padding-top: 12px;
  margin-top: 13px;
  color: #7a867f;
  font-size: 10px;
  border-top: 1px solid #eef1ee;
}

.rule-foot strong {
  color: #375f4a;
  font-size: 11px;
}

.group-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.group-table {
  margin-top: 12px;
  overflow: hidden;
  border: 1px solid #e8ece8;
  border-radius: 11px;
}

.group-table-head,
.group-table-row {
  display: grid;
  grid-template-columns: minmax(110px, 1fr) 75px minmax(145px, 1.1fr) 55px;
  gap: 10px;
  align-items: center;
  padding: 8px 11px;
}

.group-table-head {
  color: #879189;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  background: #f5f7f4;
}

.group-table-row {
  min-height: 47px;
  font-size: 11px;
  border-top: 1px solid #eef1ee;
}

.group-name {
  display: flex;
  align-items: center;
  gap: 7px;
}

.group-name i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.total-limit-row > div,
.seed-row > div {
  display: flex;
  flex-direction: column;
}

.total-limit-row span,
.seed-row strong {
  font-size: 12px;
  font-weight: 700;
}

.total-limit-row small,
.seed-row small {
  margin-top: 3px;
  color: #78847d;
  font-size: 10px;
}

.total-limit-row :deep(.n-input-number),
.seed-row :deep(.n-input-number) {
  width: 155px;
}

.final-total {
  display: flex;
  align-items: baseline;
  gap: 8px;
  color: #2f6d4f;
}

.final-total strong {
  font-size: 42px;
  line-height: 1;
  letter-spacing: -0.05em;
}

.final-total span {
  color: #77837c;
  font-size: 11px;
}

.preview-card :deep(.n-card-header__main) small {
  margin-top: 2px;
  color: #7d8982;
  font-size: 10px;
  font-weight: 400;
}

.distribution-row {
  display: grid;
  grid-template-columns: 88px 1fr 32px;
  gap: 8px;
  align-items: center;
  margin-bottom: 15px;
}

.distribution-row > div:first-child small {
  display: block;
  margin: 3px 0 0 15px;
  color: #8a948e;
  font-size: 9px;
}

.distribution-row .group-name {
  font-size: 10px;
}

.distribution-track {
  height: 7px;
  overflow: hidden;
  background: #edf1ed;
  border-radius: 8px;
}

.distribution-track span {
  display: block;
  height: 100%;
  min-width: 2px;
  border-radius: inherit;
}

.distribution-row > strong {
  font-size: 10px;
}

.audit-row {
  display: grid;
  grid-template-columns: 24px 1fr auto;
  gap: 9px;
  align-items: center;
  min-height: 43px;
  border-bottom: 1px solid #eef1ee;
}

.audit-row:last-child {
  border-bottom: 0;
}

.audit-row > span {
  color: #5f8d73;
  font-size: 9px;
  font-weight: 800;
}

.audit-row strong,
.audit-row small {
  display: block;
}

.audit-row strong {
  font-size: 10px;
}

.audit-row small {
  color: #89938e;
  font-size: 9px;
}

.audit-row em {
  color: #4d8063;
  font-size: 8px;
  font-style: normal;
  font-weight: 800;
}

.payload-card pre {
  max-height: 360px;
  padding: 12px;
  margin: 0;
  overflow: auto;
  color: #385144;
  font-size: 10px;
  line-height: 1.5;
  white-space: pre-wrap;
  background: #f4f7f4;
  border-radius: 9px;
}

@media (max-width: 1500px) {
  .builder-grid {
    grid-template-columns: minmax(520px, 1.45fr) minmax(260px, 0.72fr);
  }
}

@media (max-width: 1050px) {
  .builder-grid {
    grid-template-columns: 1fr;
  }

  .preview-column {
    grid-column: auto;
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .sampling-builder {
    padding: 18px;
  }

  .page-header {
    align-items: flex-start;
    gap: 12px;
  }

  .pipeline-strip {
    flex-wrap: wrap;
  }

  .pipeline-arrow {
    display: none;
  }

  .random-badge {
    margin-left: 0;
  }

  .enabled-rule-item {
    grid-template-columns: 1fr auto;
  }

  .enabled-rule-main {
    grid-column: 1 / -1;
  }

  .inline-rule-control {
    grid-column: 1;
  }

  .enabled-rule-item > :deep(.n-button) {
    grid-row: 2;
    grid-column: 2;
    align-self: end;
  }

  .condition-row,
  .group-table-head,
  .group-table-row {
    grid-template-columns: 1fr 1fr;
  }

  .condition-row > :last-child:nth-child(3) {
    grid-column: auto;
  }

  .group-toolbar,
  .total-limit-row,
  .seed-row {
    align-items: stretch;
    flex-direction: column;
  }

  .dual-list {
    grid-template-columns: 1fr;
  }

  .transfer-controls {
    flex-direction: row;
  }
}
</style>
