<template>
  <div>
    <template v-if="!hasOrg">
      <div style="padding: 48px; text-align: center;">
        <n-empty description="You are not a member of any organization. Contact an admin." />
      </div>
    </template>

    <template v-else-if="error">
      <div style="padding: 48px;">
        <n-result
          status="error"
          title="Failed to load datasets"
          :description="error.message || 'Please try again.'"
        />
      </div>
    </template>

    <template v-else-if="isLoading">
      <div style="padding: 48px; display: flex; justify-content: center;">
        <n-spin size="large" />
      </div>
    </template>

    <template v-else>
      <slot />
    </template>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  isLoading: boolean
  hasOrg: boolean
  error?: Error | null
}>()
</script>
