<script setup lang="ts">
import { usePagePanels } from "../../composables/usePagePanels";
import type { UsePagePanelsOptions, UsePagePanelsReturn } from "../../composables/usePagePanels";

defineOptions({ inheritAttrs: false });

const props = defineProps<UsePagePanelsOptions>();

const {
  interactionContext,
  interactionState,
  dispatchIntent,
  dashboard,
} = usePagePanels(props);

defineExpose<UsePagePanelsReturn>({
  interactionContext,
  interactionState,
  dispatchIntent,
  dashboard,
});
</script>

<template>
  <slot
    :interaction="interactionContext"
    :dashboard="dashboard"
  />
</template>
