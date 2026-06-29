<script setup lang="ts">
import { ref, watchEffect } from "vue";
import { NButton, NInput, NSpace } from "naive-ui";

const props = defineProps<{
  appliedValues: Array<string | number>;
}>();

const emit = defineEmits<{
  (e: "apply", value: Array<string | number>): void;
  (e: "close"): void;
}>();

const text = ref("");

watchEffect(() => {
  text.value = props.appliedValues.map(String).join(", ");
});

function apply(): void {
  const values = text.value
    .split(",")
    .map((part) => Number(part.trim()))
    .filter(Number.isFinite);
  emit("apply", values);
  emit("close");
}

function clear(): void {
  emit("apply", []);
  emit("close");
}
</script>

<template>
  <div class="sst-filter-popover">
    <NInput
      :value="text"
      placeholder="Defect IDs, comma separated"
      size="small"
      clearable
      @update:value="text = $event"
      @keyup.enter="apply"
    />
    <NSpace :size="4">
      <NButton size="tiny" type="primary" @click="apply">Apply</NButton>
      <NButton size="tiny" quaternary @click="clear">Clear</NButton>
    </NSpace>
  </div>
</template>

<style scoped>
.sst-filter-popover {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  max-width: min(320px, calc(100vw - 48px));
  min-width: 0;
  width: 260px;
}
</style>
