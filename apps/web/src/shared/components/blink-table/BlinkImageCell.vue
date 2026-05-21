<!--
  BlinkImageCell — display-only image cell that swaps between imageA and imageB.

  This cell does NOT own any timer; it purely responds to the external `phase` prop.
  A subtle crossfade transition is applied when the image switches.
-->
<script setup lang="ts">
import type { BlinkPhase } from "../../types/blink-table";

const props = defineProps<{
  imageA: string;
  imageB: string;
  phase: BlinkPhase;
}>();
</script>

<template>
  <div class="blink-cell">
    <Transition name="blink-crossfade" mode="out-in">
      <img
        v-if="phase === 'A'"
        :key="'a'"
        :src="imageA"
        loading="lazy"
        alt=""
        class="blink-cell-img"
      />
      <img
        v-else
        :key="'b'"
        :src="imageB"
        loading="lazy"
        alt=""
        class="blink-cell-img"
      />
    </Transition>
  </div>
</template>

<style scoped>
.blink-cell {
  position: relative;
  width: 120px;
  height: 90px;
  overflow: hidden;
  background: #111;
  border-radius: 4px;
  flex-shrink: 0;
}

.blink-cell-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  background: #111;
}

.blink-crossfade-enter-active,
.blink-crossfade-leave-active {
  transition: opacity 0.15s ease;
}

.blink-crossfade-enter-from,
.blink-crossfade-leave-to {
  opacity: 0;
}
</style>
