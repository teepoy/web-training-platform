<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

const APP_HEADER_HEIGHT = 48;
const DEFAULT_CONTENT_PADDING_PX = 24;

const props = defineProps<{ offset?: number }>();
const route = useRoute();

function parseVerticalPaddingPx(value: unknown): number {
  if (typeof value !== "string") return DEFAULT_CONTENT_PADDING_PX;
  const firstValue = value.trim().split(/\s+/)[0];
  const parsed = Number.parseFloat(firstValue);
  return Number.isFinite(parsed) ? parsed : DEFAULT_CONTENT_PADDING_PX;
}

const resolvedOffset = computed(() => {
  if (typeof props.offset === "number") return props.offset;
  const headerOffset = route.meta.hideAppHeader === true ? 0 : APP_HEADER_HEIGHT;
  return headerOffset + parseVerticalPaddingPx(route.meta.contentPadding) * 2;
});
</script>
<template>
  <div class="full-screen-layout" :style="{ height: `calc(100vh - ${resolvedOffset}px)` }">
    <slot />
  </div>
</template>
<style scoped>
.full-screen-layout { display: flex; flex-direction: column; overflow: hidden; }
</style>
