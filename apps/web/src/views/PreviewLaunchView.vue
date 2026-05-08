<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { NCard } from 'naive-ui'
import { PluginTypeSelector, type PluginCard } from '@platform/web-ui'
import { pluginRegistry } from '../core/registry'
import type { PreviewLauncherDescriptor } from '@platform/plugin-sdk'

const router = useRouter()
const message = useMessage()

const previewLaunchers = computed<PluginCard[]>(() =>
  pluginRegistry.getPreviewLaunchers('preview').map((p) => ({
    id: p.id,
    label: p.label,
    description: p.description,
    icon: p.icon,
    component: p.component,
  }))
)

const selectedLauncher = ref<PreviewLauncherDescriptor | null>(null)
const showLauncherForm = ref(false)

function handleSelectLauncher(plugin: PluginCard) {
  const launcher = pluginRegistry.getPreviewLaunchers('preview').find((p) => p.id === plugin.id)
  if (launcher) {
    selectedLauncher.value = launcher
    showLauncherForm.value = true
  }
}

function handleLauncherComplete(result: unknown) {
  showLauncherForm.value = false
  selectedLauncher.value = null
  const r = result as { sessionId?: string }
  if (r?.sessionId) {
    router.push({ name: 'preview-classify', params: { sessionId: r.sessionId } })
  }
}

function handleLauncherCancel() {
  showLauncherForm.value = false
  selectedLauncher.value = null
}
</script>

<template>
  <div style="display: flex; justify-content: center; padding: 48px 16px;">
    <NCard title="Preview Dataset" style="max-width: 560px; width: 100%;">
      <template v-if="!showLauncherForm">
        <PluginTypeSelector
          :plugins="previewLaunchers"
          title="Choose a preview source"
          @select="handleSelectLauncher"
        />
      </template>
      <template v-else-if="selectedLauncher">
        <component
          :is="selectedLauncher.component"
          :on-complete="handleLauncherComplete"
          :on-cancel="handleLauncherCancel"
        />
      </template>
    </NCard>
  </div>
</template>
