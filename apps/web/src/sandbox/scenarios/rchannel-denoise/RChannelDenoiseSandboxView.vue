<template>
  <div class="rchannel-sandbox">
    <n-spin :show="datasetLoading">
      <template v-if="datasetError">
        <n-result
          status="404"
          title="Dataset Not Found"
          description="The ImageNet-100 R-Channel dataset has not been seeded yet."
        >
          <template #footer>
            <n-space vertical align="center">
              <n-button type="primary" @click="refetchDataset">Retry</n-button>
              <n-text depth="3">
                Run <n-code>make ensure-sandbox-datasets</n-code> from the repo root to seed this dataset.
              </n-text>
            </n-space>
          </template>
        </n-result>
      </template>

      <template v-else-if="datasetId">
        <n-space vertical>
          <n-space align="center" justify="space-between">
            <n-space align="center">
              <n-h2 style="margin: 0">ImageNet-100 R-Channel Denoising</n-h2>
              <n-tag type="info" size="medium" round>
                {{ totalCount }} samples
              </n-tag>
            </n-space>
            <n-space>
              <n-button
                size="small"
                :type="prefs.layout === 'grid' ? 'primary' : 'default'"
                @click="prefs.layout = 'grid'"
              >
                Grid
              </n-button>
              <n-button
                size="small"
                :type="prefs.layout === 'list' ? 'primary' : 'default'"
                @click="prefs.layout = 'list'"
              >
                List
              </n-button>
            </n-space>
          </n-space>

          <n-text depth="3" style="max-width: 720px">
            5 R-channel grayscale images per sample: noisy 32×32, clean 32×32,
            difference 32×32, full 224×224, random crop 224×224.
            First 100 ImageNet classes, salt & pepper noise (5%).
          </n-text>

          <SampleBrowser
            :items="browserItems"
            :total-count="totalCount"
            :thumb-size="prefs.thumbSize"
            :layout="prefs.layout"
            :is-loading="sampleLoading"
            activation-mode="open"
            @load-more="loadMore"
            @open-item="onOpenItem"
          />
        </n-space>

        <n-drawer v-model:show="drawerVisible" :width="640">
          <n-drawer-content v-if="selectedSample" :title="`Sample: ${selectedSample.id.slice(0, 8)}...`">
            <n-space vertical size="large">
              <div v-for="(label, i) in IMAGE_LABELS" :key="i">
                <n-text strong>{{ label }}</n-text>
                <n-image
                  :src="selectedSample.imageSrcs[i]"
                  :img-props="{ style: { maxHeight: '320px', objectFit: 'contain' } }"
                  style="margin-top: 8px"
                />
              </div>

              <n-divider />
              <n-text strong>Metadata</n-text>
              <n-descriptions label-placement="left" :column="1" size="small" bordered>
                <n-descriptions-item
                  v-for="(value, key) in displayMetadata"
                  :key="key"
                  :label="String(key)"
                >
                  <template v-if="Array.isArray(value)">
                    [{{ (value as unknown[]).join(', ') }}]
                  </template>
                  <template v-else>
                    {{ value }}
                  </template>
                </n-descriptions-item>
              </n-descriptions>
            </n-space>
          </n-drawer-content>
        </n-drawer>
      </template>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  NButton,
  NCode,
  NDescriptions,
  NDescriptionsItem,
  NDivider,
  NDrawer,
  NDrawerContent,
  NH2,
  NImage,
  NResult,
  NSpace,
  NSpin,
  NTag,
  NText,
} from 'naive-ui'
import { useQuery } from '@tanstack/vue-query'
import {
  SampleBrowser,
  useSampleLoader,
  useSampleBrowserPrefs,
  resolveImageUris,
  listDatasets,
  type BrowserItem,
  type SampleWithLabels,
} from '@platform/web-ui'

const IMAGE_LABELS = [
  '1. Noisy 32×32 (Salt & Pepper)',
  '2. Clean 32×32',
  '3. Difference 32×32',
  '4. Full R-Channel 224×224',
  '5. Crop R-Channel 224×224',
] as const

const DATASET_NAME = 'ImageNet-100 R-Channel (10K)'

const prefs = useSampleBrowserPrefs()

// ---------------------------------------------------------------------------
// Find dataset by name
// ---------------------------------------------------------------------------
const datasetQuery = useQuery({
  queryKey: ['datasets-sandbox'],
  queryFn: listDatasets,
  retry: false,
})

const dataset = computed(() =>
  datasetQuery.data.value?.find((d) => d.name === DATASET_NAME),
)

const datasetId = computed(() => dataset.value?.id ?? null)
const datasetName = computed(() => dataset.value?.name ?? DATASET_NAME)
const datasetLoading = computed(() => datasetQuery.isLoading.value)
const datasetError = computed(
  () => datasetQuery.isError.value || (!datasetLoading.value && !dataset.value),
)

function refetchDataset() {
  datasetQuery.refetch()
}

// ---------------------------------------------------------------------------
// Sample loader
// ---------------------------------------------------------------------------
const {
  samples,
  totalCount,
  isLoading: sampleLoading,
  loadMore,
} = useSampleLoader({
  datasetId: computed(() => datasetId.value ?? ''),
  pageSize: 50,
})

// ---------------------------------------------------------------------------
// Map samples to BrowserItem[]
// ---------------------------------------------------------------------------
const browserItems = computed<BrowserItem[]>(() =>
  samples.value.map(mapSampleToBrowserItem),
)

function mapSampleToBrowserItem(s: SampleWithLabels): BrowserItem {
  return {
    id: s.id,
    imageSrcs: resolveImageUris(s.image_uris),
    metadata: s.metadata as Record<string, unknown>,
    sourceKind: 'dataset',
    currentLabel: s.latest_annotation?.label ?? (s.metadata?.label_name as string) ?? null,
    draftLabel: null,
    predictionLabel: null,
    predictionConfidence: null,
    predictionId: null,
    activationLabel: null,
  }
}

// ---------------------------------------------------------------------------
// Detail drawer
// ---------------------------------------------------------------------------
const drawerVisible = ref(false)
const selectedId = ref<string | null>(null)

const selectedSample = computed<BrowserItem | null>(() => {
  if (!selectedId.value) return null
  return browserItems.value.find((item) => item.id === selectedId.value) ?? null
})

const displayMetadata = computed(() => {
  const meta = selectedSample.value?.metadata ?? {}
  const exclude = ['view_mode']
  const filtered: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(meta)) {
    if (!exclude.includes(k)) filtered[k] = v
  }
  return filtered
})

function onOpenItem(id: string) {
  selectedId.value = id
  drawerVisible.value = true
}
</script>

<style scoped>
.rchannel-sandbox {
  padding: 24px;
}
</style>
