<script setup lang="ts">
import { computed } from "vue";
import { NSelect, type SelectOption } from "naive-ui";
import type { CreatorSummary } from "@/generated/orval/models";
import { useAuthStore } from "@/features/auth/application/store";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    creators: CreatorSummary[];
    resourceLabel?: string;
    loading?: boolean;
    disabled?: boolean;
    size?: "tiny" | "small" | "medium" | "large";
  }>(),
  {
    resourceLabel: "resources",
    loading: false,
    disabled: false,
    size: "small",
  },
);

const emit = defineEmits<{
  (event: "update:modelValue", value: string): void;
}>();

const authStore = useAuthStore();

const options = computed<SelectOption[]>(() => {
  const currentUser = authStore.user;
  const result: SelectOption[] = [
    { label: `My ${props.resourceLabel}`, value: "me" },
    { label: "All creators", value: "all" },
  ];
  for (const creator of props.creators) {
    if (creator.id === currentUser?.id) continue;
    result.push({ label: creator.name || creator.id, value: creator.id });
  }
  if (
    props.modelValue !== "me" &&
    props.modelValue !== "all" &&
    !result.some((option) => option.value === props.modelValue)
  ) {
    result.push({ label: props.modelValue, value: props.modelValue });
  }
  return result;
});
</script>

<template>
  <NSelect
    :value="props.modelValue"
    :options="options"
    :loading="props.loading"
    :disabled="props.disabled"
    :size="props.size"
    filterable
    data-testid="creator-scope-select"
    @update:value="emit('update:modelValue', String($event))"
  />
</template>
