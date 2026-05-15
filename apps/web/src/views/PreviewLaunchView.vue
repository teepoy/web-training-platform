<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { NCard } from 'naive-ui'
import { FlowTypeSelector, type FlowCard } from '@platform/web-ui'
import UpstreamPreviewLauncher from '../features/preview/components/UpstreamPreviewLauncher.vue'

const router = useRouter()
const message = useMessage()

const previewLaunchers: FlowCard[] = [
  {
    id: "preview-upstream",
    label: "Upstream Collection",
    description: "Browse a remote collection without importing it first.",
    icon: "🔍",
    component: UpstreamPreviewLauncher,
  },
]

const selectedLauncher = ref<FlowCard | null>(null)
const showLauncherForm = ref(false)

function handleSelectLauncher(plugin: FlowCard) {
  selectedLauncher.value = plugin
  showLauncherForm.value = true
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
        <FlowTypeSelector
          :flows="previewLaunchers"
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
