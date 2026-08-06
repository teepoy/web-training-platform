<script setup lang="ts">
import { computed, ref, watch } from "vue";
import {
  NAlert,
  NButton,
  NCard,
  NCheckbox,
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
} from "naive-ui";
import type { ScSampleTableFilter } from "@/features/sc/domain/sampleTable";
import {
  cloneScSamplingProgram,
  largestRemainderCounts,
  SC_SAMPLING_GROUP_FIELDS,
  scSamplingProgramError,
  type ScSamplingGroupPopulation,
  type ScSamplingProgram,
  type ScSamplingRuleId,
} from "@/features/sc/domain/samplingRules";
import { scMissingFilterOption } from "@/features/sc/domain/missingFilterValue";

interface RuleCatalogItem {
  id: ScSamplingRuleId;
  order: string;
  title: string;
  description: string;
}

const props = defineProps<{
  show: boolean;
  loading: boolean;
  availableCount: number;
  mapSelectionCount: number;
  globalFilter: ScSampleTableFilter;
  program: ScSamplingProgram;
  seed: number;
  reviewOnly: boolean;
  mapSelectionOnly: boolean;
  assignDraftLabel: boolean;
  draftLabel: string | null;
  codeLabels: Array<{ code: string; name: string }>;
  loadGroups: (field: string) => Promise<ScSamplingGroupPopulation[]>;
}>();

const emit = defineEmits<{
  (e: "update:show", show: boolean): void;
  (e: "update:program", program: ScSamplingProgram): void;
  (e: "update:seed", seed: number): void;
  (e: "update:review-only", value: boolean): void;
  (e: "update:map-selection-only", value: boolean): void;
  (e: "update:assign-draft-label", value: boolean): void;
  (e: "update:draft-label", value: string | null): void;
  (e: "scope-change"): void;
  (e: "edit-global-filter"): void;
  (e: "confirm"): void;
}>();

const catalog: RuleCatalogItem[] = [
  {
    id: "global",
    order: "01",
    title: "Global filter",
    description: "Use the workbench's combined global filter as the first eligibility stage.",
  },
  {
    id: "conditional",
    order: "02",
    title: "Conditional limit",
    description: "Cap only one matching subset while leaving other candidates eligible.",
  },
  {
    id: "quota",
    order: "03A",
    title: "Group quota",
    description: "Choose explicit counts or final composition ratios for each group.",
  },
  {
    id: "rate",
    order: "03B",
    title: "Group sampling rate",
    description: "Sample a percentage of each group's own eligible population.",
  },
  {
    id: "total",
    order: "04",
    title: "Total limit",
    description: "Cap the final cohort without implicitly filling shortfalls.",
  },
];

const message = useMessage();
const draft = ref(cloneScSamplingProgram(props.program));
const activeTab = ref<"rules" | "global">("rules");
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

const showModel = computed({
  get: () => props.show,
  set: (show: boolean) => emit("update:show", show),
});
const seedModel = computed({
  get: () => props.seed,
  set: (seed: number) => emit("update:seed", seed),
});
const reviewOnlyModel = computed({
  get: () => props.reviewOnly,
  set: (value: boolean) => emit("update:review-only", value),
});
const mapSelectionOnlyModel = computed({
  get: () => props.mapSelectionOnly,
  set: (value: boolean) => emit("update:map-selection-only", value),
});
const assignDraftLabelModel = computed({
  get: () => props.assignDraftLabel,
  set: (value: boolean) => emit("update:assign-draft-label", value),
});
const draftLabelModel = computed({
  get: () => props.draftLabel,
  set: (value: string | null) => emit("update:draft-label", value),
});

function ruleIsEnabled(id: ScSamplingRuleId): boolean {
  if (id === "global") return draft.value.globalFilterEnabled;
  if (id === "conditional") return draft.value.conditional.enabled;
  if (id === "total") return draft.value.total.enabled;
  return draft.value.group.enabled && draft.value.group.kind === id;
}

const disabledRules = computed(() => catalog.filter((item) => !ruleIsEnabled(item.id)));
const enabledRules = computed(() => catalog.filter((item) => ruleIsEnabled(item.id)));
const configuredRules = computed(() => enabledRules.value.filter((item) => item.id !== "global"));
const activeRuleCount = computed(() => enabledRules.value.length);
const globalFilterEntries = computed(() => Object.entries(props.globalFilter ?? {}));
const configurationError = computed(() => scSamplingProgramError(draft.value));
const editingRuleItem = computed(
  () => catalog.find((item) => item.id === editingRule.value) ?? null,
);
const groupRatioTotal = computed(() =>
  draft.value.group.targets.reduce((sum, target) => sum + target.amount, 0),
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
    const ratioCounts =
      draft.value.group.kind === "quota" && draft.value.group.unit === "ratio"
        ? largestRemainderCounts(draft.value.group.targets, draft.value.total.limit)
        : [];
    eligible = groupPopulations.value.reduce((sum, population) => {
      const index = draft.value.group.targets.findIndex(
        (target) => target.value === population.value,
      );
      if (index < 0) {
        return sum + (draft.value.group.unlisted === "keep" ? population.count : 0);
      }
      const target = draft.value.group.targets[index];
      if (!target) return sum;
      const planned =
        draft.value.group.kind === "rate"
          ? roundedCount(population.count * (target.amount / 100), draft.value.group.rounding)
          : draft.value.group.unit === "ratio"
            ? (ratioCounts[index] ?? 0)
            : target.amount;
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

function formatGlobalCondition(condition: ScSampleTableFilter[string]): string {
  if (condition.filterType === "set") {
    return condition.values.map(String).join(", ");
  }
  return `${condition.filter} – ${condition.filterTo}`;
}

function defaultTargetAmount(population: ScSamplingGroupPopulation, count: number): number {
  if (draft.value.group.kind === "rate") return 10;
  if (draft.value.group.unit === "ratio") return Math.floor(100 / Math.max(count, 1));
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
  if (draft.value.group.kind === "quota" && draft.value.group.unit === "ratio") {
    const counts = largestRemainderCounts(
      populations.map((population) => ({
        value: population.value,
        amount: 100 / Math.max(populations.length, 1),
      })),
      100,
    );
    if (reset || groupRatioTotal.value !== 100) {
      draft.value.group.targets.forEach((target, index) => {
        target.amount = counts[index] ?? 0;
      });
    }
  }
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
  if (id === "global") {
    draft.value.globalFilterEnabled = enabled;
    emit("update:program", cloneScSamplingProgram(draft.value));
    emit("scope-change");
  } else if (id === "conditional") {
    draft.value.conditional.enabled = enabled;
  } else if (id === "total") {
    draft.value.total.enabled = enabled;
  } else if (enabled) {
    draft.value.group.enabled = true;
    draft.value.group.kind = id;
    void loadGroupPopulations(true);
  } else if (draft.value.group.enabled && draft.value.group.kind === id) {
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
  if (id === "global") {
    activeTab.value = "global";
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

function handleGroupModeChange(): void {
  if (draft.value.group.kind === "quota" && draft.value.group.unit === "ratio") {
    draft.value.group.unlisted = "exclude";
  }
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
    :style="{ width: 'min(960px, calc(100vw - 32px))' }"
    class="review-sampling-modal"
    data-testid="review-sampling-modal"
  >
    <div class="sampling-summary">
      <div>
        <span>BASE ELIGIBLE</span>
        <strong>{{ availableCount.toLocaleString() }}</strong>
      </div>
      <span class="summary-arrow">→</span>
      <div class="summary-final">
        <span>ESTIMATED FINAL</span>
        <strong>{{ finalEstimate.toLocaleString() }}</strong>
      </div>
      <NTag round type="success">{{ activeRuleCount }} rules enabled</NTag>
    </div>

    <NTabs v-model:value="activeTab" type="line" animated>
      <NTabPane name="rules" tab="Enabled rules">
        <NCard size="small" :bordered="false" class="scope-card">
          <div class="scope-heading">
            <div>
              <strong>Candidate scope</strong>
              <small>Applied before enabled sampling rules.</small>
            </div>
            <NText depth="3">{{ availableCount.toLocaleString() }} available</NText>
          </div>
          <div class="scope-options">
            <NCheckbox v-model:checked="reviewOnlyModel" @update:checked="handleScopeChange">
              Review candidates only (has images)
            </NCheckbox>
            <NCheckbox
              v-model:checked="mapSelectionOnlyModel"
              :disabled="mapSelectionCount === 0"
              @update:checked="handleScopeChange"
            >
              Current map selection only<span v-if="mapSelectionCount > 0">
                ({{ mapSelectionCount }})</span
              >
            </NCheckbox>
          </div>
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
            <button type="button" class="rule-copy" @click="openRuleConfiguration(item.id)">
              <span>{{ item.order }}</span>
              <div>
                <strong>{{ item.title }}</strong>
                <small>{{ item.description }}</small>
              </div>
            </button>
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
                  {{ draft.group.targets.length }} groups ·
                  {{ draft.group.kind === "rate" ? "rate" : draft.group.unit }}
                </NTag>
              </template>
            </div>
            <NButton size="small" secondary @click="openRuleConfiguration(item.id)"> Edit </NButton>
          </article>
          <div v-if="configuredRules.length === 0" class="empty-rules">
            No limiting rule enabled. Use Manage sampling rules to add one.
          </div>
        </div>

        <div class="sampling-options-grid">
          <NCard size="small" :bordered="false">
            <label class="field-label">Random seed</label>
            <NInputNumber
              v-model:value="seedModel"
              :min="0"
              :max="Number.MAX_SAFE_INTEGER"
              :precision="0"
            />
            <NText depth="3">The same scope, rules, and seed produce the same cohort.</NText>
          </NCard>
          <NCard size="small" :bordered="false">
            <NCheckbox v-model:checked="assignDraftLabelModel">
              Assign draft label to sampled defects
            </NCheckbox>
            <NSelect
              v-model:value="draftLabelModel"
              :disabled="!assignDraftLabelModel"
              :options="
                codeLabels.map((item) => ({
                  label: `${item.code} · ${item.name}`,
                  value: item.code,
                }))
              "
              placeholder="Select draft label"
            />
          </NCard>
        </div>
      </NTabPane>

      <NTabPane name="global" tab="Global filter">
        <NCard :bordered="false" class="global-filter-card">
          <div class="global-filter-heading">
            <div>
              <strong>Workbench Global Filter</strong>
              <small>
                This is the shared complex filter used by the map, table, gallery, sampling, and
                Train &amp; Predict.
              </small>
            </div>
            <NTag :type="draft.globalFilterEnabled ? 'success' : 'default'" round>
              {{ draft.globalFilterEnabled ? "Enabled" : "Disabled for sampling" }}
            </NTag>
          </div>
          <div v-if="globalFilterEntries.length > 0" class="global-condition-list">
            <div v-for="[field, condition] in globalFilterEntries" :key="field">
              <strong>{{ field }}</strong>
              <span>{{ formatGlobalCondition(condition) }}</span>
            </div>
          </div>
          <NAlert v-else type="info" :show-icon="false">
            No Global Filter conditions are active. Open the full editor to combine fields and
            ranges.
          </NAlert>
          <div class="global-filter-actions">
            <NButton secondary @click="emit('edit-global-filter')">Edit Global Filter</NButton>
            <NButton
              v-if="!draft.globalFilterEnabled"
              type="primary"
              secondary
              @click="setRuleEnabled('global', true)"
            >
              Enable for sampling
            </NButton>
          </div>
        </NCard>
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
            :disabled="
              availableCount === 0 ||
              !!configurationError ||
              (assignDraftLabelModel && !draftLabelModel)
            "
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
    :style="{ width: 'min(820px, calc(100vw - 32px))' }"
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
      Group quota (03A) and group sampling rate (03B) are mutually exclusive.
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
    :style="{ width: 'min(760px, calc(100vw - 32px))' }"
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

    <div v-else-if="editingRule === 'quota' || editingRule === 'rate'" class="rule-config-panel">
      <div class="group-config-toolbar">
        <NSelect
          v-model:value="draft.group.field"
          :options="SC_SAMPLING_GROUP_FIELDS"
          aria-label="Group field"
        />
        <NRadioGroup
          v-if="draft.group.kind === 'quota'"
          v-model:value="draft.group.unit"
          @update:value="handleGroupModeChange"
        >
          <NRadioButton value="count">Count</NRadioButton>
          <NRadioButton value="ratio">Final ratio</NRadioButton>
        </NRadioGroup>
        <NSelect
          v-else
          v-model:value="draft.group.rounding"
          :options="[
            { label: 'Nearest', value: 'nearest' },
            { label: 'Floor', value: 'floor' },
            { label: 'Ceil', value: 'ceil' },
          ]"
          aria-label="Rate rounding"
        />
        <NSelect
          v-model:value="draft.group.unlisted"
          :disabled="draft.group.kind === 'quota' && draft.group.unit === 'ratio'"
          :options="[
            { label: 'Exclude unlisted', value: 'exclude' },
            { label: 'Keep unlisted', value: 'keep' },
          ]"
          aria-label="Unlisted group policy"
        />
      </div>

      <NAlert
        v-if="draft.group.kind === 'quota' && draft.group.unit === 'ratio' && !draft.total.enabled"
        type="error"
        :show-icon="false"
      >
        Final ratios require Total limit to be enabled.
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
              :max="draft.group.kind === 'rate' || draft.group.unit === 'ratio' ? 100 : undefined"
              :precision="draft.group.kind === 'rate' || draft.group.unit === 'ratio' ? 2 : 0"
              :aria-label="`${population.value} sampling target`"
            >
              <template v-if="draft.group.kind === 'rate' || draft.group.unit === 'ratio'" #suffix
                >%</template
              >
            </NInputNumber>
          </div>
          <div v-if="groupPopulations.length === 0" class="empty-rules">
            No groups in this candidate scope.
          </div>
        </div>
      </NSpin>
      <NText v-if="draft.group.kind === 'quota' && draft.group.unit === 'ratio'" depth="3">
        Current final ratio total: {{ groupRatioTotal }}%
      </NText>
    </div>

    <div v-else-if="editingRule === 'total'" class="rule-config-panel">
      <label class="field-label">Maximum final samples</label>
      <NInputNumber v-model:value="draft.total.limit" :min="1" :precision="0" />
      <NText depth="3">This is an upper bound; the pipeline does not fill rule shortfalls.</NText>
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
.sampling-summary,
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

.sampling-summary {
  padding: 12px 16px;
  margin-bottom: 10px;
  background: color-mix(in srgb, var(--cv-primary, #4c80f0) 8%, var(--cv-card-bg, #fff));
  border: 1px solid color-mix(in srgb, var(--cv-primary, #4c80f0) 18%, transparent);
  border-radius: 12px;
}

.sampling-summary > div {
  display: flex;
  flex-direction: column;
}

.sampling-summary span,
.scope-heading small,
.rules-heading small,
.global-filter-heading small,
.rule-copy small,
.rule-list-item small,
.field-label {
  color: var(--cv-text-secondary, #737373);
  font-size: 11px;
}

.sampling-summary strong {
  font-size: 21px;
}

.summary-arrow {
  color: var(--cv-text-disabled, #aaa);
}

.summary-final {
  margin-right: auto;
}

.scope-card,
.sampling-options-grid :deep(.n-card),
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

.inline-control label,
.field-label {
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

.sampling-options-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}

.sampling-options-grid :deep(.n-input-number),
.sampling-options-grid :deep(.n-select) {
  width: 100%;
  margin: 6px 0;
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

.global-condition-list > div {
  display: grid;
  grid-template-columns: minmax(130px, 0.4fr) 1fr;
  gap: 12px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--cv-divider, #ededed);
}

.global-condition-list > div:last-child {
  border-bottom: 0;
}

.global-filter-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
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
  .sampling-options-grid,
  .condition-grid,
  .group-config-toolbar,
  .dual-list {
    grid-template-columns: 1fr;
  }

  .transfer-controls {
    flex-direction: row;
  }

  .sampling-summary {
    flex-wrap: wrap;
  }
}
</style>
