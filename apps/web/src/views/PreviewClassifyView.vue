<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import {
  NImage, NButton, NSpace, NSpin, NAlert, NModal, NRadioGroup, NRadio,
  NCard, NDivider, NTag, NImageGroup
} from 'naive-ui'
import { getPreviewSession, startPreviewPersist } from '../api'
import { usePreviewLoader } from '../composables/usePreviewLoader'
import type { PreviewSession, PreviewPersistScope, PreviewItem } from '../types'
import PreviewItemDrawer from '../components/preview/PreviewItemDrawer.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()

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
      <div class="preview-layout">
        <!-- Image grid -->
        <div class="preview-main">
          <div class="preview-grid">
            <NImageGroup>
              <div
                v-for="item in loader.items.value"
                :key="item.upstream_item_id"
                class="preview-grid-item"
                @click="selectItem(item)"
                style="cursor: pointer"
              >
                <NImage
                  :src="item.image_uris[0]"
                  object-fit="cover"
                  width="160"
                  height="120"
                  lazy
                />
              </div>
            </NImageGroup>
          </div>

          <div v-if="loader.hasMore.value" class="preview-load-more">
            <NButton
              :loading="loader.isLoading.value"
              @click="loader.loadMore()"
            >
              Load More
            </NButton>
          </div>
          <div v-else-if="loader.initialized.value" class="preview-load-more">
            <span style="color: var(--n-text-color-3); font-size: 13px;">All items loaded</span>
          </div>
        </div>

        <!-- Sidebar -->
        <div class="preview-sidebar">
          <NCard size="small">
            <NSpace vertical>
              <div>
                <div class="sidebar-label">Collection</div>
                <div class="sidebar-value">{{ session?.collection_ref }}</div>
              </div>
              <div>
                <div class="sidebar-label">Loaded</div>
                <div class="sidebar-value">
                  {{ loader.loadedCount.value }}
                  <span v-if="session?.estimated_total"> / ~{{ session.estimated_total }}</span>
                </div>
              </div>
              <NDivider style="margin: 8px 0" />
              <NAlert
                v-if="!session?.classification_enabled"
                type="info"
                :show-icon="false"
                style="font-size: 12px;"
              >
                Classification disabled until dataset is persisted.
              </NAlert>
              <NButton
                type="primary"
                block
                @click="showPersistModal = true"
              >
                Persist Dataset
              </NButton>
            </NSpace>
          </NCard>
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
.preview-layout {
  display: flex;
  gap: 16px;
  padding: 16px;
  height: 100%;
  overflow: hidden;
}
.preview-main {
  flex: 1;
  overflow-y: auto;
}
.preview-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.preview-grid-item {
  border-radius: 4px;
  overflow: hidden;
  background: var(--n-color-modal);
}
.preview-load-more {
  display: flex;
  justify-content: center;
  padding: 16px 0;
}
.preview-sidebar {
  width: 260px;
  flex-shrink: 0;
}
.sidebar-label {
  font-size: 11px;
  color: var(--n-text-color-3);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 2px;
}
.sidebar-value {
  font-size: 14px;
  font-weight: 500;
}
</style>
