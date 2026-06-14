<template>
  <div data-testid="view-sc-patch-image">
    <!-- Empty state -->
    <n-empty
      v-if="allItems.length === 0 && !loading"
      description="No samples found for this view"
      style="margin-top: 24px"
    />

    <!-- Error state -->
    <n-result
      v-else-if="error"
      status="error"
      title="Failed to load view data"
      :description="error"
    >
      <template #footer>
        <n-button @click="retry">Retry</n-button>
      </template>
    </n-result>

    <!-- Loaded state -->
    <template v-else>
      <div ref="scrollContainerRef" class="sc-viewport">
        <div :style="{ height: `${rowVirtualizer.getTotalSize()}px`, position: 'relative' }">
          <div
            v-for="row in rowVirtualizer.getVirtualItems()"
            :key="String(row.key)"
            :style="{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              transform: `translateY(${row.start}px)`,
            }"
          >
            <div class="sc-grid-row">
              <div
                v-for="(item, colIdx) in rows[row.index]"
                :key="item.sample_id"
                class="sc-card"
              >
                <div class="sc-card-images">
                  <div class="sc-image-group">
                    <span class="sc-image-label">Template</span>
                    <img
                      v-if="item.template_url"
                      :src="item.template_url"
                      class="sc-image"
                      @error="onImageError"
                    />
                    <span v-else class="sc-image-na">N/A</span>
                  </div>
                  <div class="sc-image-group">
                    <span class="sc-image-label">Defective</span>
                    <img
                      v-if="item.defective_url"
                      :src="item.defective_url"
                      class="sc-image"
                      @error="onImageError"
                    />
                    <span v-else class="sc-image-na">N/A</span>
                  </div>
                  <div v-if="item.difference_url" class="sc-image-group">
                    <span class="sc-image-label">Difference</span>
                    <img
                      :src="item.difference_url"
                      class="sc-image"
                      @error="onImageError"
                    />
                  </div>
                </div>

                <div class="sc-card-meta">
                  <n-text depth="3" style="font-size: 12px">
                    {{ item.sample_id }}
                  </n-text>
                </div>

                <!-- Review images section (review_image_v1 only) -->
                <n-collapse v-if="viewType === 'review_image_v1' && (item as ScReviewImageV1Row).review_images?.length" class="sc-review-collapse">
                  <n-collapse-item title="Review Images" name="review">
                    <div class="sc-review-strip">
                      <div
                        v-for="revImg in (item as ScReviewImageV1Row).review_images"
                        :key="revImg.image_id"
                        class="sc-review-item"
                      >
                        <img
                          :src="revImg.image_url"
                          class="sc-review-image"
                          @error="onImageError"
                        />
                        <n-text depth="3" style="font-size: 10px; text-align: center">
                          {{ revImg.image_type }}
                        </n-text>
                      </div>
                    </div>
                  </n-collapse-item>
                </n-collapse>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Pagination: Load More -->
      <div v-if="allItems.length < total" class="sc-load-more">
        <n-button
          :loading="loading"
          :disabled="loading"
          @click="loadMore"
        >
          Load More
        </n-button>
        <n-text depth="3" style="margin-left: 12px">
          {{ allItems.length }} of {{ total }}
        </n-text>
      </div>
    </template>

    <!-- Loading overlay -->
    <n-spin v-if="loading && allItems.length === 0" style="display: flex; justify-content: center; padding: 48px" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useVirtualizer } from "@tanstack/vue-virtual";
import { withAuthQueryParams } from "@/shared/api/client";
import {
  NButton,
  NCollapse,
  NCollapseItem,
  NEmpty,
  NResult,
  NSpin,
  NText,
} from "naive-ui";

import { scPatchUrl, scReviewUrl, normalizeScImageRole } from "@/features/sc/domain/models";

interface ScSampleImage {
  role?: string;
  image_id?: string;
  image_type?: string;
  content_type?: string;
  url?: string;
}

interface ScSampleApiRow {
  sample_id: string;
  inspection_time?: string;
  wafer_key?: number;
  defect_id?: string;
  wafer_x?: number;
  wafer_y?: number;
  rough_bin?: number;
  class_number?: number;
  images?: ScSampleImage[];
}

interface ScPatchImageV1Row {
  sample_id: string;
  template_url: string;
  defective_url: string;
  difference_url: string;
}

interface ScReviewImageV1Row {
  sample_id: string;
  template_url: string;
  defective_url: string;
  difference_url: string;
  review_images: Array<{
    image_id?: number;
    image_url?: string;
    image_name?: string;
    image_type?: string;
  }>;
}

function patchRoleImageUrl(row: ScSampleApiRow, role: string): string {
  const img = (row.images ?? []).find(
    (i) => (i.role || "").toLowerCase() === role.toLowerCase()
  );
  if (img?.url) {
    return withAuthQueryParams(img.url);
  }
  if (row.inspection_time === undefined || row.wafer_key === undefined || row.defect_id === undefined) {
    return "";
  }
  const patchRole = normalizeScImageRole(role);
  if (!patchRole) return "";
  return scPatchUrl(row.inspection_time, row.wafer_key, row.defect_id, patchRole);
}

function reviewRoleImageUrl(row: ScSampleApiRow, image: ScSampleImage): string {
  if (image.url) {
    return withAuthQueryParams(image.url);
  }
  if (row.inspection_time === undefined || row.wafer_key === undefined || row.defect_id === undefined) {
    return "";
  }
  const imageId = Number(image.image_id);
  return Number.isFinite(imageId)
    ? scReviewUrl(row.inspection_time, row.wafer_key, row.defect_id, imageId)
    : "";
}

function mapApiRow(row: ScSampleApiRow): ScPatchImageV1Row | ScReviewImageV1Row {
  const base: ScPatchImageV1Row = {
    sample_id: row.sample_id,
    template_url: patchRoleImageUrl(row, "patch_template"),
    defective_url: patchRoleImageUrl(row, "patch_defective"),
    difference_url: patchRoleImageUrl(row, "patch_difference"),
  };
  if (viewType === "review_image_v1") {
    const reviewImages = (row.images ?? [])
      .filter((img) => img.role === "review")
      .map((img) => ({
        image_id: img.image_id ? Number(img.image_id) : undefined,
        image_url: reviewRoleImageUrl(row, img),
        image_name: img.image_id,
        image_type: img.image_type,
      }));
    return { ...base, review_images: reviewImages };
  }
  return base;
}

import { listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet } from "@/generated/orval/endpoints/api";

const props = withDefaults(
  defineProps<{
    datasetId?: string;
    items?: unknown[];
    total?: number;
    viewType?: string;
  }>(),
  {
    items: () => [],
    total: 0,
    viewType: "patch_image_v1",
  },
);

const viewType = props.viewType ?? "patch_image_v1";

const LIMIT = 50;

const allItems = ref<(ScPatchImageV1Row | ScReviewImageV1Row)[]>(
  (props.items as (ScPatchImageV1Row | ScReviewImageV1Row)[]) ?? [],
);
const currentOffset = ref(props.items?.length ?? 0);
const loading = ref(false);
const error = ref<string | null>(null);

/* ---- Virtualizer ---- */
const scrollContainerRef = ref<HTMLDivElement | null>(null);

const rows = computed(() => {
  const result: (ScPatchImageV1Row | ScReviewImageV1Row)[][] = [];
  for (let i = 0; i < allItems.value.length; i += 3) {
    result.push(allItems.value.slice(i, i + 3));
  }
  return result;
});

const rowVirtualizer = useVirtualizer({
  get count() { return rows.value.length; },
  getScrollElement: () => scrollContainerRef.value,
  estimateSize: () => 220,
  overscan: 2,
});
/* ------------------- */

const placeholderDataUrl =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='80' viewBox='0 0 80 80'%3E%3Crect width='80' height='80' fill='%23f3f3f3'/%3E%3Cpath d='M10 70 L30 40 L45 55 L55 35 L70 65 Z' fill='%23ddd'/%3E%3Ccircle cx='58' cy='28' r='6' fill='%23ddd'/%3E%3Ctext x='40' y='72' text-anchor='middle' font-size='8' fill='%23999'%3EBroken%3C/text%3E%3C/svg%3E";

function onImageError(e: Event) {
  const img = e.target as HTMLImageElement;
  img.src = placeholderDataUrl;
}

async function loadMore() {
  if (loading.value) return;
  if (!props.datasetId) return;

  loading.value = true;
  error.value = null;

  try {
    const result = await listViewSamplesApiV1DatasetsDatasetIdViewsViewTypeSamplesGet(
      props.datasetId!,
      viewType,
      { offset: currentOffset.value, limit: LIMIT },
    );
    const rawItems =
      ((result.data as unknown as { items: ScSampleApiRow[] }) ?? {}).items ?? [];
    const items = rawItems.map(mapApiRow);
    allItems.value = [...allItems.value, ...items];
    currentOffset.value += LIMIT;
  } catch (err) {
    error.value =
      err instanceof Error ? err.message : "Unknown error loading view data";
  } finally {
    loading.value = false;
  }
}

function retry() {
  error.value = null;
  loadMore();
}

onMounted(() => {
  if (allItems.value.length === 0 && props.datasetId) {
    loadMore();
  }
});
</script>

<style scoped>
.sc-viewport {
  height: calc(100vh - 300px);
  overflow-y: auto;
}

.sc-grid-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  padding: 0 4px;
}

.sc-card {
  border: 1px solid var(--n-border-color, #e5e5e5);
  border-radius: 8px;
  padding: 12px;
  background: var(--n-color, #fff);
}

.sc-card-images {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

.sc-image-group {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 0;
}

.sc-image-label {
  font-size: 10px;
  color: var(--n-text-color-3, #999);
  margin-bottom: 4px;
  text-align: center;
}

.sc-image {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid var(--n-border-color, #eee);
}

.sc-image-na {
  width: 100%;
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  border: 1px dashed var(--n-border-color, #ddd);
  background: var(--n-color-secondary, #fafafa);
  color: var(--n-text-color-3, #bbb);
  font-size: 12px;
}

.sc-card-meta {
  display: flex;
  justify-content: center;
  margin-bottom: 4px;
}

.sc-review-collapse {
  margin-top: 8px;
}

.sc-review-strip {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 4px;
}

.sc-review-item {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 80px;
}

.sc-review-image {
  width: 72px;
  height: 72px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid var(--n-border-color, #eee);
}

.sc-load-more {
  display: flex;
  justify-content: center;
  align-items: center;
  margin-top: 24px;
}
</style>
