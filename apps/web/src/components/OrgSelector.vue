<template>
  <template v-if="authStore.isAuthenticated">
    <n-select
      v-if="orgStore.organizations.length > 0"
      :options="orgOptions"
      :value="orgStore.currentOrgId"
      placeholder="Select org"
      size="small"
      style="width: 180px"
      @update:value="(val: string) => orgStore.setCurrentOrg(val)"
    />
    <span v-else style="font-size: 12px; color: var(--n-text-color-disabled)">No organizations</span>
  </template>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '../stores/auth'
import { useOrgStore } from '../stores/org'

const authStore = useAuthStore()
const orgStore = useOrgStore()

const orgOptions = computed(() =>
  orgStore.organizations.map(org => ({ label: org.name, value: org.id }))
)
</script>
