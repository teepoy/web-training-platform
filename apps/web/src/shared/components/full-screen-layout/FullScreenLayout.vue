<script setup lang="ts">
withDefaults(defineProps<{ offset?: number }>(), { offset: 96 });
</script>
<template>
  <div class="full-screen-layout" :style="{ height: `calc(100vh - ${offset}px)` }">
    <slot />
  </div>
</template>
<style scoped>
.full-screen-layout { display: flex; flex-direction: column; overflow: hidden; }
</style>
