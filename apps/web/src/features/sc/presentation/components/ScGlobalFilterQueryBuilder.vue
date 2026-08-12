<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { NButton, NSelect } from "naive-ui";
import {
  QueryBuilder,
  createQueryBuilderId,
  type QueryBuilderGroup,
  type QueryBuilderRule,
} from "@/shared/components/query-builder";
import {
  cloneScFilterCondition,
  cloneScGlobalFilter,
  emptyScGlobalFilter,
  isScGlobalFilterGroup,
  scGlobalFilterConditionCount,
  type ScFilterCondition,
  type ScGlobalFilter,
  type ScGlobalFilterGroup,
  type ScGlobalFilterItemSource,
  type ScGlobalFilterNode,
} from "@/features/sc/domain/globalFilter";
import { scMissingFilterOption } from "@/features/sc/domain/missingFilterValue";
import type { ScDataColumn } from "@/features/sc/domain/workbenchDataSource";
import { scGlobalFilterColumns, type ScFilterColumnDefinition } from "./scSampleTableColumns";
import ScRangeFilterMenu from "./ScRangeFilterMenu.vue";
import ScSetFilterMenu from "./ScSetFilterMenu.vue";
import ScTextFilterMenu from "./ScTextFilterMenu.vue";

interface ScQueryRuleValue {
  field: string | null;
  condition: ScFilterCondition | null;
  source: ScGlobalFilterItemSource;
}

type ScQueryRule = QueryBuilderRule<ScQueryRuleValue>;
type ScQueryGroup = QueryBuilderGroup<ScQueryRuleValue>;
type UpdateRule = (rule: ScQueryRule) => void;

const ROOT_GROUP_ID = "sc-global-filter-root";

const props = withDefaults(
  defineProps<{
    filter: ScGlobalFilter;
    columns?: ScDataColumn[];
    distinctValues: Record<string, Array<string | number>>;
    numericRanges?: Record<string, { min: number; max: number } | null>;
    numericRangeLoading?: Record<string, boolean>;
    numericRangeErrors?: Record<string, boolean>;
    showReclassifyColumns?: boolean;
    resetKey?: string | number;
  }>(),
  {
    numericRanges: () => ({}),
    numericRangeLoading: () => ({}),
    numericRangeErrors: () => ({}),
  },
);

const emit = defineEmits<{
  (event: "update:filter", filter: ScGlobalFilter): void;
  (event: "search-options", payload: { field: string; search: string }): void;
  (event: "request-range", payload: { field: string; itemId?: string }): void;
}>();

const builderModel = ref<ScQueryGroup>(toBuilderRoot(props.filter));
const searchByRule = ref<Record<string, string>>({});
const setDraftByRule = ref<Record<string, string[]>>({});
const rangeDraftByRule = ref<Record<string, { min: number | null; max: number | null }>>({});
const editingRuleId = ref<string | null>(null);

const activeCount = computed(() => scGlobalFilterConditionCount(props.filter));
const hasBuilderNodes = computed(() => builderModel.value.items.length > 0);
const fieldDefinitions = computed(() =>
  scGlobalFilterColumns(props.columns ?? [], props.showReclassifyColumns === true),
);
const fieldOptions = computed(() =>
  fieldDefinitions.value.map((definition) => ({
    label: definition.title,
    value: String(definition.key),
  })),
);

function definitionFor(field: string | null): ScFilterColumnDefinition | undefined {
  if (!field) return undefined;
  return fieldDefinitions.value.find((definition) => String(definition.key) === field);
}

function toBuilderRoot(filter: ScGlobalFilter): ScQueryGroup {
  return {
    kind: "group",
    id: ROOT_GROUP_ID,
    combinator: filter.combinator,
    items: filter.items.map(toBuilderNode),
  };
}

function toBuilderNode(node: ScGlobalFilterNode): ScQueryRule | ScQueryGroup {
  if (isScGlobalFilterGroup(node)) {
    return {
      kind: "group",
      id: node.id,
      combinator: node.combinator,
      items: node.items.map(toBuilderNode),
    };
  }
  return {
    kind: "rule",
    id: node.id,
    value: {
      field: node.field,
      condition: cloneScFilterCondition(node.condition),
      source: { ...node.source },
    },
  };
}

function fromBuilderRoot(group: ScQueryGroup): ScGlobalFilter {
  const items = group.items.flatMap(fromBuilderNode);
  if (items.length === 0) return emptyScGlobalFilter();
  return {
    combinator: group.combinator,
    items,
  };
}

function fromBuilderNode(node: ScQueryRule | ScQueryGroup): ScGlobalFilterNode[] {
  if (node.kind === "group") {
    const items = node.items.flatMap(fromBuilderNode);
    if (items.length === 0) return [];
    const group: ScGlobalFilterGroup = {
      kind: "group",
      id: node.id,
      combinator: node.combinator,
      items,
    };
    return [group];
  }
  if (!node.value.field || !node.value.condition) return [];
  return [
    {
      id: node.id,
      field: node.value.field,
      condition: cloneScFilterCondition(node.value.condition),
      source: { ...node.value.source },
    },
  ];
}

function createDraftRule(): ScQueryRule {
  return {
    kind: "rule",
    id: createQueryBuilderId(),
    value: { field: null, condition: null, source: { kind: "manual" } },
  };
}

function updateBuilder(next: ScQueryGroup): void {
  builderModel.value = next;
  const effectiveFilter = fromBuilderRoot(next);
  if (JSON.stringify(effectiveFilter) !== JSON.stringify(props.filter)) {
    emit("update:filter", effectiveFilter);
  }
}

function updateRuleValue(rule: ScQueryRule, update: UpdateRule, value: ScQueryRuleValue): void {
  update({ ...rule, value });
}

function updateRuleField(rule: ScQueryRule, update: UpdateRule, field: string | null): void {
  updateRuleValue(rule, update, { ...rule.value, field, condition: null });
  setDraftByRule.value[rule.id] = [];
  rangeDraftByRule.value[rule.id] = { min: null, max: null };
  editingRuleId.value = field ? rule.id : null;
  const definition = definitionFor(field);
  if (field && definition) prepareEditor(rule, definition);
}

function prepareEditor(rule: ScQueryRule, definition: ScFilterColumnDefinition): void {
  const field = rule.value.field;
  if (!field) return;
  if (definition.filter === "range") {
    getRangeDraft(rule);
    emit("request-range", { field, itemId: rule.id });
  } else {
    setDraftByRule.value[rule.id] = setFilterValues(rule).map(String);
  }
}

function toggleEditor(rule: ScQueryRule): void {
  if (editingRuleId.value === rule.id) {
    editingRuleId.value = null;
    return;
  }
  const definition = definitionFor(rule.value.field);
  if (!definition) return;
  editingRuleId.value = rule.id;
  prepareEditor(rule, definition);
}

function setFilterValues(rule: ScQueryRule): Array<string | number> {
  return rule.value.condition?.filterType === "set" ? rule.value.condition.values : [];
}

function setFilterExcluded(rule: ScQueryRule): boolean {
  return rule.value.condition?.filterType === "set" && rule.value.condition.exclude === true;
}

function optionsFor(rule: ScQueryRule): Array<{ label: string; value: string | number }> {
  const field = rule.value.field;
  if (!field) return [];
  const values = new Map<string, string | number>();
  for (const value of props.distinctValues[field] ?? []) values.set(String(value), value);
  for (const value of setFilterValues(rule)) values.set(String(value), value);
  return Array.from(values.values())
    .sort((left, right) =>
      typeof left === "number" && typeof right === "number"
        ? left - right
        : String(left).localeCompare(String(right), undefined, { numeric: true }),
    )
    .map((value) => ({
      label:
        scMissingFilterOption(field)?.value === value
          ? (scMissingFilterOption(field)?.label ?? String(value))
          : String(value),
      value,
    }));
}

function normalizeFilterValue(field: string, value: string | number): string | number {
  if (field !== "defect_id") return value;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : value;
}

function applySetFilter(
  rule: ScQueryRule,
  update: UpdateRule,
  remove: () => void,
  values: Array<string | number>,
  exclude = false,
): void {
  const field = rule.value.field;
  if (!field) return;
  if (values.length === 0) {
    remove();
    return;
  }
  updateRuleValue(rule, update, {
    ...rule.value,
    condition: {
      filterType: "set",
      values: values.map((value) => normalizeFilterValue(field, value)),
      ...(exclude ? { exclude: true } : {}),
    },
  });
  editingRuleId.value = null;
}

function getRangeDraft(rule: ScQueryRule): { min: number | null; max: number | null } {
  if (!rangeDraftByRule.value[rule.id]) {
    const condition = rule.value.condition;
    rangeDraftByRule.value[rule.id] =
      condition?.filterType === "number" && condition.type === "inRange"
        ? { min: condition.filter, max: condition.filterTo }
        : { min: null, max: null };
  }
  return rangeDraftByRule.value[rule.id]!;
}

function applyRangeFilter(rule: ScQueryRule, update: UpdateRule): void {
  const draft = getRangeDraft(rule);
  if (draft.min === null || draft.max === null || draft.min > draft.max) return;
  updateRuleValue(rule, update, {
    ...rule.value,
    condition: {
      filterType: "number",
      type: "inRange",
      filter: draft.min,
      filterTo: draft.max,
    },
  });
  editingRuleId.value = null;
}

function itemOperator(rule: ScQueryRule): string {
  if (rule.value.condition?.filterType === "number") return "is between";
  return rule.value.condition?.exclude ? "excludes" : "is any of";
}

function itemValueSummary(rule: ScQueryRule): string {
  const condition = rule.value.condition;
  if (!condition) return "—";
  if (condition.filterType === "set") {
    const values = condition.values.map(String);
    if (values.length === 0) return "No values";
    const visible = values.slice(0, 3).join(", ");
    return values.length > 3 ? `${visible} +${values.length - 3}` : visible;
  }
  return `${condition.filter} – ${condition.filterTo}`;
}

function clearAll(): void {
  resetLocalEditor();
  builderModel.value = toBuilderRoot(emptyScGlobalFilter());
  emit("update:filter", emptyScGlobalFilter());
}

function resetLocalEditor(): void {
  searchByRule.value = {};
  setDraftByRule.value = {};
  rangeDraftByRule.value = {};
  editingRuleId.value = null;
}

watch(
  () => props.filter,
  (filter) => {
    const currentEffectiveFilter = fromBuilderRoot(builderModel.value);
    if (JSON.stringify(currentEffectiveFilter) !== JSON.stringify(filter)) {
      builderModel.value = toBuilderRoot(cloneScGlobalFilter(filter));
    }
  },
  { deep: true },
);

watch(
  () => props.numericRanges,
  (ranges) => {
    for (const [ruleId, range] of Object.entries(ranges)) {
      if (!range) continue;
      const draft = rangeDraftByRule.value[ruleId];
      if (!draft || (draft.min === null && draft.max === null)) {
        rangeDraftByRule.value[ruleId] = { ...range };
      }
    }
  },
  { deep: true },
);

watch(
  () => props.resetKey,
  (resetKey, previousResetKey) => {
    if (previousResetKey === undefined || resetKey === previousResetKey) return;
    resetLocalEditor();
    builderModel.value = toBuilderRoot(props.filter);
  },
);
</script>

<template>
  <div class="sc-filter-query-builder">
    <div class="sc-filter-query-builder__toolbar">
      <span v-if="activeCount > 0" class="sc-filter-query-builder__count">
        {{ activeCount }} condition{{ activeCount === 1 ? "" : "s" }}
      </span>
      <NButton
        size="small"
        quaternary
        type="primary"
        :disabled="!hasBuilderNodes"
        @click="clearAll"
      >
        Clear all
      </NButton>
    </div>

    <QueryBuilder
      :model-value="builderModel"
      :create-rule="createDraftRule"
      root
      @update:model-value="updateBuilder"
    >
      <template #rule="{ rule, update, remove }">
        <div class="sc-filter-rule">
          <div v-if="rule.value.field && rule.value.condition" class="sc-filter-rule__summary">
            <span class="sc-filter-rule__property">
              {{ definitionFor(rule.value.field)?.title ?? rule.value.field }}
            </span>
            <span class="sc-filter-rule__operator">{{ itemOperator(rule) }}</span>
            <span class="sc-filter-rule__value">{{ itemValueSummary(rule) }}</span>
            <NButton size="tiny" secondary @click="toggleEditor(rule)">
              {{ editingRuleId === rule.id ? "Close" : "Edit" }}
            </NButton>
          </div>

          <div v-else class="sc-filter-rule__draft">
            <NSelect
              class="sc-filter-rule__property-select"
              data-testid="query-rule-property"
              placeholder="Property"
              filterable
              :options="fieldOptions"
              :value="rule.value.field"
              @update:value="updateRuleField(rule, update, $event)"
            />
          </div>

          <div
            v-if="rule.value.field && (!rule.value.condition || editingRuleId === rule.id)"
            class="sc-filter-rule__editor"
          >
            <ScTextFilterMenu
              v-if="rule.value.field === 'defect_id'"
              :applied-values="setFilterValues(rule)"
              :exclude="setFilterExcluded(rule)"
              @apply="(values, exclude) => applySetFilter(rule, update, remove, values, exclude)"
              @close="editingRuleId = null"
            />
            <ScSetFilterMenu
              v-else-if="definitionFor(rule.value.field)?.filter === 'set'"
              :search="searchByRule[rule.id] ?? ''"
              :applied-values="setFilterValues(rule)"
              :draft-values="setDraftByRule[rule.id] ?? setFilterValues(rule).map(String)"
              :options="optionsFor(rule)"
              @update:search="searchByRule[rule.id] = $event"
              @update:draft-values="setDraftByRule[rule.id] = $event"
              @search-options="emit('search-options', { field: rule.value.field!, search: $event })"
              @apply="applySetFilter(rule, update, remove, $event)"
              @close="editingRuleId = null"
            />
            <ScRangeFilterMenu
              v-else
              :min="getRangeDraft(rule).min"
              :max="getRangeDraft(rule).max"
              :loading="numericRangeLoading[rule.id] === true"
              :range-unavailable="numericRangeErrors[rule.id] === true"
              @update:min="getRangeDraft(rule).min = $event"
              @update:max="getRangeDraft(rule).max = $event"
              @apply="applyRangeFilter(rule, update)"
              @clear="remove"
              @close="editingRuleId = null"
            />
          </div>
        </div>
      </template>
    </QueryBuilder>
  </div>
</template>

<style scoped>
.sc-filter-query-builder {
  min-height: 0;
}

.sc-filter-query-builder__toolbar {
  display: flex;
  min-height: 28px;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-bottom: 8px;
}

.sc-filter-query-builder__count {
  color: color-mix(in srgb, currentColor 58%, transparent);
  font-size: 12px;
}

.sc-filter-rule,
.sc-filter-rule__summary,
.sc-filter-rule__draft {
  min-width: 0;
}

.sc-filter-rule__summary {
  display: grid;
  align-items: center;
  gap: 10px;
  grid-template-columns: minmax(110px, 0.8fr) minmax(80px, auto) minmax(120px, 1.4fr) auto;
}

.sc-filter-rule__property,
.sc-filter-rule__value {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sc-filter-rule__property {
  font-weight: 600;
}

.sc-filter-rule__operator {
  color: color-mix(in srgb, currentColor 60%, transparent);
  font-size: 12px;
}

.sc-filter-rule__value {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
}

.sc-filter-rule__property-select {
  max-width: 260px;
}

.sc-filter-rule__editor {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid color-mix(in srgb, currentColor 12%, transparent);
}

.sc-filter-rule__editor :deep(.sst-filter-popover) {
  width: 100%;
  max-width: none;
  padding: 0;
}

@media (max-width: 720px) {
  .sc-filter-rule__summary {
    grid-template-columns: minmax(100px, 1fr) auto;
  }

  .sc-filter-rule__operator,
  .sc-filter-rule__value {
    grid-column: 1 / -1;
  }
}
</style>
