<template>
  <n-layout has-sider style="height: 100vh">
    <n-layout-sider
      bordered
      show-trigger
      collapse-mode="width"
      :collapsed-width="64"
      :width="240"
      :collapsed="collapsed"
      @collapse="collapsed = true"
      @expand="collapsed = false"
    >
      <n-menu
        :collapsed="collapsed"
        :options="menuOptions"
        :value="activeRoute"
        @update:value="(key: string) => router.push(key)"
      />
    </n-layout-sider>
    <n-layout vertical>
      <n-layout-header bordered style="height: 48px; display: flex; align-items: center; padding: 0 16px; justify-content: space-between">
        <span style="font-weight: 600">Admin</span>
        <n-button text type="primary" @click="router.push('/datasets')">← Back to App</n-button>
      </n-layout-header>
      <n-layout-content style="padding: 24px; overflow-y: auto">
        <RouterView />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute, RouterView } from 'vue-router'

const router = useRouter()
const route = useRoute()

const collapsed = ref(false)

const menuOptions = [
  { label: 'Dashboard', key: '/admin/dashboard' },
  { label: 'Preset Catalog', key: '/admin/presets' }
]

const activeRoute = computed(() => route.path)
</script>
