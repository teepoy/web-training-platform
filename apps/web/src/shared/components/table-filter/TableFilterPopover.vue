<script setup lang="ts">
import { NButton, NSpace } from "naive-ui";
import { useI18n } from "vue-i18n";

withDefaults(
  defineProps<{
    variant?: "set" | "text" | "range";
    applyDisabled?: boolean;
  }>(),
  { variant: "range", applyDisabled: false },
);

const emit = defineEmits<{
  (event: "clear"): void;
  (event: "cancel"): void;
  (event: "apply"): void;
}>();
const { t } = useI18n();
</script>

<template>
  <div class="sst-filter-popover" :class="`sst-filter-popover--${variant}`">
    <slot />
    <NSpace :size="4">
      <NButton size="tiny" quaternary @click="emit('clear')">{{ t("common.clear") }}</NButton>
      <NButton size="tiny" quaternary @click="emit('cancel')">{{ t("common.cancel") }}</NButton>
      <NButton size="tiny" type="primary" :disabled="applyDisabled" @click="emit('apply')">
        {{ t("common.apply") }}
      </NButton>
    </NSpace>
  </div>
</template>

<style scoped>
.sst-filter-popover {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: min(320px, calc(100vw - 48px));
  min-width: 0;
  padding: 8px;
}

.sst-filter-popover--set,
.sst-filter-popover--text {
  width: 260px;
}
</style>
