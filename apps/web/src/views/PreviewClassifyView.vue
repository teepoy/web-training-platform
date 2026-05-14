<script setup lang="ts">
import { ref, onMounted, computed, provide } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NButton, NSpace, NSpin, NAlert, NModal, NRadioGroup, NRadio, NRadioButton
} from 'naive-ui'
import {
  getPreviewSession,
  startPreviewPersist,
  type PreviewSession,
  type PreviewPersistScope,
  type PreviewItem,
} from '@platform/web-data/preview'
import { usePreviewLoader } from '@platform/web-ui'
import type { BrowserItem, WaferPoint } from '../types'
import { BrowserSidebar, PreviewItemDrawer, SampleBrowser } from '@platform/web-ui'
import { previewPanels } from '../features/classify/config'
import {
  COLLAPSED_SIDEBAR_WIDTH,
  MAX_SIDEBAR_WIDTH,
  MIN_SIDEBAR_WIDTH,
  useSampleBrowserPrefs,
  injectWaferPanelData,
  metadataNumber,
  metadataString,
  useDataPipeline as createDataPipeline,
  DATA_PIPELINE_KEY,
} from '@platform/web-ui'
import { widgetComponentMap } from '../components/classify/widgetMap'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const prefs = useSampleBrowserPrefs()

const sessionId = computed(() => route.params.sessionId as string)

const session = ref<PreviewSession | null>(null)
const sessionError = ref<string | null>(null)
const sessionLoading = ref(true)

const loader = usePreviewLoader({ sessionId: sessionId.value, pageSize: 20 })

const showPersistModal = ref(false)
const persistScope = ref<PreviewPersistScope>('entire_collection')
const isPersisting = ref(false)

const selectedItem = ref<PreviewItem | null>(null)
const showDrawer = ref(false)

const browserItems = computed<BrowserItem[]>(() => {
  return loader.items.value.map(item => ({
    id: item.upstream_item_id,
    imageSrcs: item.image_uris,
    metadata: item.metadata || {},
    sourceKind: 'preview',
    currentLabel: null,
    draftLabel: null,
    predictionLabel: null,
    predictionConfidence: null,
    predictionId: null,
    activationLabel: null,
  }))
})

// ── DataPipeline (wafer-map is read-only, no filtering) ──
const pipeline = createDataPipeline<BrowserItem>(browserItems)
pipeline.register('wafer-map')
provide(DATA_PIPELINE_KEY, pipeline)

const previewWaferPoints = computed<WaferPoint[]>(() => {
  return loader.items.value.flatMap((item) => {
    const x = metadataNumber(item.metadata, 'wafer_x')
    const y = metadataNumber(item.metadata, 'wafer_y')
    if (x == null || y == null) {
      return []
    }
    return [{
      id: metadataString(item.metadata, 'point_id') ?? item.upstream_item_id,
      x,
      y,
    }]
  })
})

const previewSidebarPanels = computed(() =>
  injectWaferPanelData(previewPanels, previewWaferPoints.value, 'browser-items'),
)

function selectItem(item: PreviewItem) {
  selectedItem.value = item
  showDrawer.value = true
}

onMounted(async () => {
  try {
    session.value = await getPreviewSession(sessionId.value)
    await loader.loadMore()
  } catch (err) {
    sessionError.value = 'Preview session not found or expired.'
  } finally {
    sessionLoading.value = false
  }
})

async function handlePersist() {
  isPersisting.value = true
  try {
    const status = await startPreviewPersist(sessionId.value, persistScope.value)
    showPersistModal.value = false
    message.success('Dataset persisted successfully!')
    await router.push(`/datasets/${status.dataset_id}/classify?previewPersistSession=${sessionId.value}`)
  } catch (err) {
    message.error('Failed to persist: ' + String(err))
  } finally {
    isPersisting.value = false
  }
}
</script>

<template>
  <div class="preview-workspace">
    <!-- Loading / Error states -->
    <div v-if="sessionLoading" class="preview-center">
      <NSpin size="large" />
    </div>
    <div v-else-if="sessionError" class="preview-center">
      <NAlert type="error" :title="sessionError" />
    </div>

    <!-- Main workspace -->
    <template v-else>
      <!-- Toolbar -->
      <div class="preview-toolbar">
        <NRadioGroup v-model:value="prefs.layout" size="small">
          <NRadioButton value="grid">Grid</NRadioButton>
          <NRadioButton value="list">List</NRadioButton>
        </NRadioGroup>
      </div>

      <!-- Optional: notice about classification disabled -->
      <div v-if="!session?.classification_enabled" class="preview-notice-bar">
        <NAlert type="info" :show-icon="false" style="margin: 8px 16px;">
          Classification disabled until dataset is persisted.
        </NAlert>
      </div>

      <div class="preview-layout">
        <!-- Image grid -->
        <SampleBrowser
          :items="browserItems"
          :total-count="loader.estimatedTotal.value ?? loader.loadedCount.value"
          :thumb-size="prefs.thumbSize"
          :layout="prefs.layout"
          :is-loading="loader.isLoading.value"
          :selection-enabled="false"
          :show-checkboxes="false"
          :show-label-rail="false"
          :show-bottom-bar="false"
          activation-mode="open"
          @open-item="(id) => selectItem(loader.items.value.find(i => i.upstream_item_id === id)!)"
          @load-more="loader.loadMore()"
        />

        <!-- Sidebar area -->
        <div class="preview-sidebar-container" :class="{ 'collapsed': prefs.sidebarCollapsed }">
          <div class="preview-sidebar-actions">
            <NButton type="primary" block @click="showPersistModal = true">
              Persist Dataset
            </NButton>
          </div>
          <!-- BrowserSidebar provides its own borders, we wrap it just to add the persist button above -->
          <div style="flex: 1; min-height: 0; display: flex;">
            <BrowserSidebar
              :panels="previewSidebarPanels"
              :collapsed="prefs.sidebarCollapsed"
              :sidebar-width="prefs.sidebarWidth"
              :min-sidebar-width="MIN_SIDEBAR_WIDTH"
              :max-sidebar-width="MAX_SIDEBAR_WIDTH"
              :collapsed-sidebar-width="COLLAPSED_SIDEBAR_WIDTH"
              :component-resolver="(key) => widgetComponentMap[key] ?? null"
              @update:collapsed="prefs.setSidebarCollapsed"
              @update:sidebar-width="prefs.setSidebarWidth"
              style="border-left: none;"
            />
          </div>
        </div>
      </div>
    </template>

    <!-- Preview Item Drawer -->
    <PreviewItemDrawer v-model:show="showDrawer" :item="selectedItem" />

    <!-- Persist modal -->
    <NModal v-model:show="showPersistModal" preset="card" title="Persist Dataset" style="max-width: 420px;">
      <NSpace vertical size="large">
        <p style="margin: 0; color: var(--n-text-color-2);">
          Choose what to persist as a new dataset:
        </p>
        <NRadioGroup v-model:value="persistScope">
          <NSpace vertical>
            <NRadio value="entire_collection">Entire collection (recommended)</NRadio>
            <NRadio value="loaded_items_only">Currently loaded items only</NRadio>
          </NSpace>
        </NRadioGroup>
        <NSpace justify="end">
          <NButton @click="showPersistModal = false" :disabled="isPersisting">Cancel</NButton>
          <NButton type="primary" :loading="isPersisting" @click="handlePersist">Persist</NButton>
        </NSpace>
      </NSpace>
    </NModal>
  </div>
</template>

<style scoped>
.preview-toolbar {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  flex-shrink: 0;
}
.preview-workspace {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.preview-center {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 300px;
}
.preview-notice-bar {
  flex-shrink: 0;
}
.preview-layout {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.preview-sidebar-container {
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--cv-border, rgba(255, 255, 255, 0.12));
  background: var(--cv-card-bg, #1e1e2e);
  transition: width 0.2s, min-width 0.2s;
}
.preview-sidebar-actions {
  padding: 12px;
  border-bottom: 1px solid var(--cv-border, rgba(255, 255, 255, 0.08));
}
.preview-sidebar-container.collapsed .preview-sidebar-actions {
  display: none;
}
</style>
