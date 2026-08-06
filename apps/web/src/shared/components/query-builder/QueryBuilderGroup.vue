<script setup lang="ts">
import { ref } from "vue";
import { NButton, NButtonGroup } from "naive-ui";
import {
  createQueryBuilderGroup,
  isQueryBuilderGroup,
  type QueryBuilderCombinator,
  type QueryBuilderGroup,
  type QueryBuilderRule,
} from "./types";

type RuleValue = unknown;

defineSlots<{
  rule(props: {
    rule: QueryBuilderRule<RuleValue>;
    update: (rule: QueryBuilderRule<RuleValue>) => void;
    remove: () => void;
  }): unknown;
}>();

const props = withDefaults(
  defineProps<{
    modelValue: QueryBuilderGroup<RuleValue>;
    createRule: () => QueryBuilderRule<RuleValue>;
    root?: boolean;
    depth?: number;
  }>(),
  { root: false, depth: 0 },
);

const emit = defineEmits<{
  (event: "update:modelValue", value: QueryBuilderGroup<RuleValue>): void;
  (event: "delete"): void;
}>();

const draggedNodeId = ref<string | null>(null);

function updateCombinator(combinator: QueryBuilderCombinator): void {
  emit("update:modelValue", { ...props.modelValue, combinator });
}

function appendRule(): void {
  emit("update:modelValue", {
    ...props.modelValue,
    items: [...props.modelValue.items, props.createRule()],
  });
}

function appendGroup(): void {
  emit("update:modelValue", {
    ...props.modelValue,
    items: [...props.modelValue.items, createQueryBuilderGroup<RuleValue>()],
  });
}

function replaceNode(
  nodeId: string,
  replacement: QueryBuilderGroup<RuleValue> | QueryBuilderRule<RuleValue>,
): void {
  emit("update:modelValue", {
    ...props.modelValue,
    items: props.modelValue.items.map((node) => (node.id === nodeId ? replacement : node)),
  });
}

function deleteNode(nodeId: string): void {
  emit("update:modelValue", {
    ...props.modelValue,
    items: props.modelValue.items.filter((node) => node.id !== nodeId),
  });
}

function onDrop(targetNodeId: string): void {
  const sourceNodeId = draggedNodeId.value;
  draggedNodeId.value = null;
  if (!sourceNodeId || sourceNodeId === targetNodeId) return;
  const sourceIndex = props.modelValue.items.findIndex((node) => node.id === sourceNodeId);
  const targetIndex = props.modelValue.items.findIndex((node) => node.id === targetNodeId);
  if (sourceIndex < 0 || targetIndex < 0) return;
  const items = [...props.modelValue.items];
  const [moved] = items.splice(sourceIndex, 1);
  if (!moved) return;
  items.splice(targetIndex, 0, moved);
  emit("update:modelValue", { ...props.modelValue, items });
}
</script>

<template>
  <section
    class="query-builder"
    :class="{ 'query-builder--root': root }"
    :data-query-builder-group-id="modelValue.id"
  >
    <header class="query-builder__header">
      <NButtonGroup size="tiny" class="query-builder__combinator" data-testid="query-combinator">
        <NButton
          :type="modelValue.combinator === 'and' ? 'primary' : 'default'"
          :secondary="modelValue.combinator === 'and'"
          data-testid="query-combinator-and"
          @click="updateCombinator('and')"
        >
          AND
        </NButton>
        <NButton
          :type="modelValue.combinator === 'or' ? 'primary' : 'default'"
          :secondary="modelValue.combinator === 'or'"
          data-testid="query-combinator-or"
          @click="updateCombinator('or')"
        >
          OR
        </NButton>
      </NButtonGroup>

      <div class="query-builder__actions">
        <NButton
          size="tiny"
          quaternary
          type="primary"
          data-testid="query-add-condition"
          @click="appendRule"
        >
          + Condition
        </NButton>
        <NButton
          size="tiny"
          quaternary
          type="primary"
          data-testid="query-add-group"
          @click="appendGroup"
        >
          + Group
        </NButton>
        <NButton
          v-if="!root"
          size="tiny"
          quaternary
          type="error"
          data-testid="query-delete-group"
          @click="emit('delete')"
        >
          Delete group
        </NButton>
      </div>
    </header>

    <div v-if="modelValue.items.length > 0" class="query-builder__items">
      <template v-for="(node, index) in modelValue.items" :key="node.id">
        <div v-if="index > 0" class="query-builder__join">
          {{ modelValue.combinator.toUpperCase() }}
        </div>

        <div
          class="query-builder__node"
          :data-query-builder-node-id="node.id"
          draggable="true"
          @dragstart="draggedNodeId = node.id"
          @dragover.prevent
          @drop="onDrop(node.id)"
        >
          <span class="query-builder__drag" aria-label="Drag query item">⋮⋮</span>

          <QueryBuilderGroup
            v-if="isQueryBuilderGroup(node)"
            class="query-builder__nested"
            :model-value="node"
            :create-rule="createRule"
            :depth="depth + 1"
            @update:model-value="replaceNode(node.id, $event)"
            @delete="deleteNode(node.id)"
          >
            <template #rule="{ rule, update, remove }">
              <slot name="rule" :rule="rule" :update="update" :remove="remove" />
            </template>
          </QueryBuilderGroup>

          <div v-else class="query-builder__rule">
            <slot
              name="rule"
              :rule="node"
              :update="(rule: QueryBuilderRule<RuleValue>) => replaceNode(node.id, rule)"
              :remove="() => deleteNode(node.id)"
            />
            <NButton
              class="query-builder__delete-rule"
              size="tiny"
              quaternary
              type="error"
              data-testid="query-delete-condition"
              @click="deleteNode(node.id)"
            >
              Delete
            </NButton>
          </div>
        </div>
      </template>
    </div>

    <div v-else class="query-builder__empty">No conditions</div>
  </section>
</template>

<style scoped>
.query-builder {
  min-width: 0;
  padding: 10px;
  border: 1px solid color-mix(in srgb, currentColor 16%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, currentColor 3%, transparent);
}

.query-builder--root {
  padding: 0;
  border: 0;
  background: transparent;
}

.query-builder__header,
.query-builder__actions {
  display: flex;
  align-items: center;
}

.query-builder__header {
  justify-content: space-between;
  gap: 12px;
}

.query-builder__actions {
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 2px;
}

.query-builder__items {
  min-width: 0;
  margin-top: 10px;
  padding-left: 12px;
  border-left: 2px solid color-mix(in srgb, currentColor 12%, transparent);
}

.query-builder__join {
  width: max-content;
  margin: 4px 0 4px -8px;
  padding: 1px 6px;
  color: var(--n-primary-color, currentColor);
  border-radius: 999px;
  background: color-mix(in srgb, currentColor 7%, transparent);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.query-builder__node {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  gap: 6px;
}

.query-builder__drag {
  flex: 0 0 auto;
  padding-top: 12px;
  color: color-mix(in srgb, currentColor 42%, transparent);
  cursor: grab;
  user-select: none;
}

.query-builder__nested,
.query-builder__rule {
  flex: 1;
  min-width: 0;
}

.query-builder__rule {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 7px 8px;
  border: 1px solid color-mix(in srgb, currentColor 14%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, currentColor 2%, transparent);
}

.query-builder__rule > :first-child {
  flex: 1;
  min-width: 0;
}

.query-builder__delete-rule {
  flex: 0 0 auto;
}

.query-builder__empty {
  margin-top: 10px;
  padding: 18px;
  color: color-mix(in srgb, currentColor 48%, transparent);
  border: 1px dashed color-mix(in srgb, currentColor 14%, transparent);
  border-radius: 8px;
  text-align: center;
  font-size: 12px;
}

@media (max-width: 720px) {
  .query-builder__header {
    align-items: flex-start;
  }

  .query-builder__items {
    padding-left: 6px;
  }
}
</style>
