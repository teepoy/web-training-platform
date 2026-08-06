<script setup lang="ts" generic="TRuleValue">
import type { QueryBuilderGroup, QueryBuilderRule } from "./types";
import QueryBuilderGroupView from "./QueryBuilderGroup.vue";

const props = withDefaults(
  defineProps<{
    modelValue: QueryBuilderGroup<TRuleValue>;
    createRule: () => QueryBuilderRule<TRuleValue>;
    root?: boolean;
    depth?: number;
  }>(),
  { root: false, depth: 0 },
);

const emit = defineEmits<{
  (event: "update:modelValue", value: QueryBuilderGroup<TRuleValue>): void;
  (event: "delete"): void;
}>();

defineSlots<{
  rule(props: {
    rule: QueryBuilderRule<TRuleValue>;
    update: (rule: QueryBuilderRule<TRuleValue>) => void;
    remove: () => void;
  }): unknown;
}>();

function toInternalGroup(group: QueryBuilderGroup<TRuleValue>): QueryBuilderGroup<unknown> {
  return group as QueryBuilderGroup<unknown>;
}

function toInternalRuleFactory(): QueryBuilderRule<unknown> {
  return props.createRule() as QueryBuilderRule<unknown>;
}

function emitInternalGroup(group: QueryBuilderGroup<unknown>): void {
  emit("update:modelValue", group as QueryBuilderGroup<TRuleValue>);
}

function toPublicRule(rule: QueryBuilderRule<unknown>): QueryBuilderRule<TRuleValue> {
  return rule as QueryBuilderRule<TRuleValue>;
}

function updateInternalRule(
  update: (rule: QueryBuilderRule<unknown>) => void,
  rule: QueryBuilderRule<TRuleValue>,
): void {
  update(rule as QueryBuilderRule<unknown>);
}
</script>

<template>
  <QueryBuilderGroupView
    :model-value="toInternalGroup(modelValue)"
    :create-rule="toInternalRuleFactory"
    :root="root"
    :depth="depth"
    @update:model-value="emitInternalGroup"
    @delete="emit('delete')"
  >
    <template #rule="{ rule, update, remove }">
      <slot
        name="rule"
        :rule="toPublicRule(rule)"
        :update="(nextRule) => updateInternalRule(update, nextRule)"
        :remove="remove"
      />
    </template>
  </QueryBuilderGroupView>
</template>
