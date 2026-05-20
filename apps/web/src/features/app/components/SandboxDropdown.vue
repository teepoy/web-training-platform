<template>
  <template v-if="isDev">
    <n-dropdown
      trigger="click"
      :options="dropdownOptions"
      @select="handleSelect"
    >
      <n-button size="small" secondary>
        Sandbox
      </n-button>
    </n-dropdown>
  </template>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { sandboxDemos } from '../../../sandbox/scenarios/registry'

const isDev = import.meta.env.DEV
const router = useRouter()

const dropdownOptions = computed(() =>
  sandboxDemos.map(demo => ({
    label: demo.name,
    key: demo.route
  }))
)

function handleSelect(key: string) {
  router.push(key)
}
</script>
