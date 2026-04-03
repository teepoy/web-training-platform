<template>
  <n-drawer
    :show="show"
    :width="520"
    placement="right"
    @update:show="(val: boolean) => { if (!val) emit('close') }"
  >
    <n-drawer-content title="Sample Detail" :native-scrollbar="false" closable @close="emit('close')">
      <n-scrollbar>
        <div v-if="!sampleId" style="padding: 24px">
          <n-empty description="No sample selected" />
        </div>

        <div v-else style="padding: 0 4px">
          <!-- ================================================================ -->
          <!-- 1. Image Preview                                                  -->
          <!-- ================================================================ -->
          <n-divider title-placement="left">
            <span style="font-size: 13px; font-weight: 600">Image Preview</span>
          </n-divider>

          <div style="margin-bottom: 16px">
            <div v-if="sampleQuery.isLoading.value" style="display: flex; justify-content: center; padding: 32px">
              <n-spin size="medium" />
            </div>
            <div v-else-if="sampleQuery.isError.value" style="padding: 16px">
              <n-alert type="error" title="Failed to load sample" />
            </div>
            <template v-else-if="sample">
              <div v-if="resolvedUris.length === 0 || (resolvedUris.length === 1 && resolvedUris[0] === fallbackPlaceholder)">
                <n-empty description="No images" />
              </div>
              <n-image-group v-else>
                <n-space wrap>
                  <n-image
                    v-for="(src, idx) in resolvedUris"
                    :key="idx"
                    :src="src"
                    width="120"
                    height="120"
                    object-fit="cover"
                    style="border-radius: 6px; border: 1px solid #eee"
                  />
                </n-space>
              </n-image-group>
            </template>
          </div>

          <!-- ================================================================ -->
          <!-- 2. Metadata                                                       -->
          <!-- ================================================================ -->
          <n-divider title-placement="left">
            <span style="font-size: 13px; font-weight: 600">Metadata</span>
          </n-divider>

          <div style="margin-bottom: 16px">
            <div v-if="sampleQuery.isLoading.value" style="display: flex; justify-content: center; padding: 16px">
              <n-spin size="small" />
            </div>
            <template v-else-if="sample">
              <pre style="margin: 0; padding: 10px; background: #f6f6f6; border-radius: 6px; font-size: 12px; white-space: pre-wrap; word-break: break-all">{{ metadataJson }}</pre>
            </template>
          </div>

          <!-- ================================================================ -->
          <!-- 3. Annotations                                                    -->
          <!-- ================================================================ -->
          <n-divider title-placement="left">
            <span style="font-size: 13px; font-weight: 600">Annotations</span>
          </n-divider>

          <div style="margin-bottom: 16px">
            <div v-if="annotationsQuery.isLoading.value" style="display: flex; justify-content: center; padding: 16px">
              <n-spin size="small" />
            </div>
            <div v-else-if="annotationsQuery.isError.value" style="padding: 8px">
              <n-alert type="error" title="Failed to load annotations" />
            </div>
            <template v-else>
              <n-empty v-if="annotations.length === 0" description="No annotations yet" style="margin-bottom: 12px" />
              <div
                v-for="ann in annotations"
                :key="ann.id"
                style="display: flex; align-items: flex-start; gap: 8px; padding: 8px; border: 1px solid #eee; border-radius: 6px; margin-bottom: 8px"
              >
                <!-- Edit mode -->
                <template v-if="editingAnnotationId === ann.id">
                  <div style="flex: 1; display: flex; flex-direction: column; gap: 6px">
                    <n-select
                      v-if="labelSpace.length > 0"
                      v-model:value="editingLabel"
                      :options="labelSpaceOptions"
                      placeholder="Select label"
                      size="small"
                    />
                    <n-input
                      v-else
                      v-model:value="editingLabel"
                      placeholder="Enter label"
                      size="small"
                    />
                    <div style="display: flex; gap: 6px">
                      <n-button
                        size="small"
                        type="primary"
                        :loading="updateAnnotationMutation.isPending.value"
                        @click="saveAnnotation(ann.id)"
                      >
                        Save
                      </n-button>
                      <n-button size="small" @click="cancelEdit">Cancel</n-button>
                    </div>
                  </div>
                </template>

                <!-- View mode -->
                <template v-else>
                  <div style="flex: 1">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px">
                      <n-tag type="info" size="small">{{ ann.label }}</n-tag>
                      <span style="font-size: 11px; color: #888">{{ ann.created_by }}</span>
                      <span style="font-size: 11px; color: #bbb">{{ formatDate(ann.created_at) }}</span>
                    </div>
                    <div style="font-size: 11px; color: #aaa; font-family: monospace">{{ ann.id.slice(0, 8) }}…</div>
                  </div>
                  <n-button
                    size="small"
                    quaternary
                    @click="startEdit(ann)"
                  >
                    Edit
                  </n-button>
                  <n-popconfirm
                    positive-text="Delete"
                    negative-text="Cancel"
                    @positive-click="deleteAnnot(ann.id)"
                  >
                    <template #trigger>
                      <n-button size="small" quaternary type="error">Delete</n-button>
                    </template>
                    Delete this annotation?
                  </n-popconfirm>
                </template>
              </div>

              <!-- Add new annotation -->
              <div style="padding: 12px; border: 1px dashed #ccc; border-radius: 6px; margin-top: 8px">
                <div style="font-size: 12px; color: #666; margin-bottom: 8px; font-weight: 600">Add Annotation</div>
                <div style="display: flex; flex-direction: column; gap: 8px">
                  <n-select
                    v-if="labelSpace.length > 0"
                    v-model:value="newAnnotationLabel"
                    :options="labelSpaceOptions"
                    placeholder="Select label"
                    size="small"
                    clearable
                  />
                  <n-input
                    v-else
                    v-model:value="newAnnotationLabel"
                    placeholder="Enter label"
                    size="small"
                  />
                  <n-input
                    v-model:value="newAnnotationCreatedBy"
                    placeholder="Created by"
                    size="small"
                  />
                  <n-button
                    type="primary"
                    size="small"
                    :loading="createAnnotationMutation.isPending.value"
                    :disabled="!newAnnotationLabel"
                    @click="addAnnotation"
                  >
                    Add
                  </n-button>
                </div>
              </div>
            </template>
          </div>

          <!-- ================================================================ -->
          <!-- 4. Replace Image                                                  -->
          <!-- ================================================================ -->
          <n-divider title-placement="left">
            <span style="font-size: 13px; font-weight: 600">Replace Image</span>
          </n-divider>

          <div style="margin-bottom: 16px">
            <input
              type="file"
              accept="image/*"
              style="display: none"
              ref="replaceFileInputRef"
              @change="onReplaceFileChange"
            />
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px">
              <n-button size="small" @click="(replaceFileInputRef as HTMLInputElement)?.click()">
                Choose File
              </n-button>
              <span v-if="replaceFile" style="font-size: 12px; color: #666">{{ replaceFile.name }}</span>
            </div>
            <n-image
              v-if="replacePreviewUrl"
              :src="replacePreviewUrl"
              width="120"
              height="120"
              object-fit="cover"
              style="border-radius: 6px; border: 1px solid #eee; margin-bottom: 8px; display: block"
            />
            <n-button
              v-if="replaceFile"
              type="primary"
              size="small"
              :loading="uploadingImage"
              @click="doUpload"
            >
              Upload
            </n-button>
          </div>

          <!-- ================================================================ -->
          <!-- 5. Find Similar                                                  -->
          <!-- ================================================================ -->
          <n-divider title-placement="left">
            <span style="font-size: 13px; font-weight: 600">Find Similar</span>
          </n-divider>

          <div style="margin-bottom: 24px">
            <!-- Button + loading state -->
            <n-button
              size="small"
              type="default"
              :loading="findSimilarLoading"
              @click="doFindSimilar"
            >
              Find Similar
            </n-button>

            <!-- Error -->
            <n-alert v-if="findSimilarError" type="error" :title="findSimilarError" style="margin-top: 8px" />

            <!-- Results panel -->
            <div v-if="similarNeighbors.length > 0" style="margin-top: 12px">
              <div style="font-size: 12px; color: #888; margin-bottom: 8px">
                {{ similarNeighbors.length }} similar samples
              </div>
              <div
                v-for="nb in similarNeighbors"
                :key="nb.sample_id"
                style="display: flex; align-items: center; gap: 10px; padding: 6px; border: 1px solid #eee; border-radius: 6px; margin-bottom: 6px; cursor: pointer"
                @click="emit('select-sample', nb.sample_id)"
              >
                <n-image
                  :src="nb.previewUri"
                  width="48"
                  height="48"
                  object-fit="cover"
                  style="border-radius: 4px; flex-shrink: 0"
                  preview-disabled
                />
                <div style="flex: 1; min-width: 0">
                  <div style="font-size: 11px; color: #666; font-family: monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap">
                    {{ nb.sample_id.slice(0, 12) }}…
                  </div>
                  <div style="font-size: 12px; color: #333; margin-top: 2px">
                    Score: {{ (nb.score * 100).toFixed(1) }}%
                  </div>
                </div>
              </div>
            </div>

            <!-- Empty state after search -->
            <div v-else-if="findSimilarSearched && !findSimilarLoading" style="margin-top: 8px">
              <n-empty description="No similar samples found" />
            </div>
          </div>
        </div>
      </n-scrollbar>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useQuery, useMutation, useQueryClient } from "@tanstack/vue-query";
import {
  NDrawer,
  NDrawerContent,
  NScrollbar,
  NImage,
  NImageGroup,
  NTag,
  NPopconfirm,
  NSelect,
  NInput,
  NButton,
  NEmpty,
  NSpin,
  NDivider,
  NSpace,
  NAlert,
} from "naive-ui";
import { api } from "../api";
import type { SimilarityResponse } from "../api";
import { resolveImageUris } from "../utils/imageAdapters";
import type { Annotation } from "../types";

// ---------------------------------------------------------------------------
// Props / Emits
// ---------------------------------------------------------------------------
const props = defineProps<{
  sampleId: string | null;
  datasetId: string;
  labelSpace: string[];
  show: boolean;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "select-sample", sampleId: string): void;
}>();

// ---------------------------------------------------------------------------
// Fallback placeholder (must match imageAdapters.ts internal constant)
// ---------------------------------------------------------------------------
const fallbackPlaceholder =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='64' height='64'%3E%3Crect width='64' height='64' fill='%23e0e0e0'/%3E%3Ctext x='50%25' y='54%25' dominant-baseline='middle' text-anchor='middle' fill='%23999' font-size='10'%3ENo img%3C/text%3E%3C/svg%3E";

// ---------------------------------------------------------------------------
// Query client
// ---------------------------------------------------------------------------
const qc = useQueryClient();

// ---------------------------------------------------------------------------
// Fetch sample
// ---------------------------------------------------------------------------
const sampleQuery = useQuery({
  queryKey: computed(() => ["sample", props.sampleId]),
  queryFn: () => api.getSample(props.sampleId!),
  enabled: computed(() => !!props.sampleId),
});

const sample = computed(() => sampleQuery.data.value ?? null);

const resolvedUris = computed(() => {
  if (!sample.value) return [];
  return resolveImageUris(sample.value.image_uris);
});

const metadataJson = computed(() =>
  sample.value ? JSON.stringify(sample.value.metadata, null, 2) : "{}"
);

// ---------------------------------------------------------------------------
// Fetch annotations
// ---------------------------------------------------------------------------
const annotationsQuery = useQuery({
  queryKey: computed(() => ["annotations", props.sampleId]),
  queryFn: () => api.listAnnotationsForSample(props.sampleId!),
  enabled: computed(() => !!props.sampleId),
});

const annotations = computed(() => annotationsQuery.data.value ?? []);

// ---------------------------------------------------------------------------
// Label space options
// ---------------------------------------------------------------------------
const labelSpaceOptions = computed(() =>
  props.labelSpace.map((l) => ({ label: l, value: l }))
);

// ---------------------------------------------------------------------------
// Annotation edit state
// ---------------------------------------------------------------------------
const editingAnnotationId = ref<string | null>(null);
const editingLabel = ref("");

function startEdit(ann: Annotation) {
  editingAnnotationId.value = ann.id;
  editingLabel.value = ann.label;
}

function cancelEdit() {
  editingAnnotationId.value = null;
  editingLabel.value = "";
}

const updateAnnotationMutation = useMutation({
  mutationFn: ({ id, label }: { id: string; label: string }) =>
    api.updateAnnotation(id, { label }),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["annotations", props.sampleId] });
    cancelEdit();
  },
});

function saveAnnotation(id: string) {
  if (!editingLabel.value) return;
  updateAnnotationMutation.mutate({ id, label: editingLabel.value });
}

const deleteAnnotationMutation = useMutation({
  mutationFn: (id: string) => api.deleteAnnotation(id),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["annotations", props.sampleId] });
  },
});

function deleteAnnot(id: string) {
  deleteAnnotationMutation.mutate(id);
}

// ---------------------------------------------------------------------------
// Add annotation state
// ---------------------------------------------------------------------------
const newAnnotationLabel = ref("");
const newAnnotationCreatedBy = ref("web-user");

const createAnnotationMutation = useMutation({
  mutationFn: (vars: { sample_id: string; label: string; created_by: string }) =>
    api.createAnnotation(vars),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["annotations", props.sampleId] });
    newAnnotationLabel.value = "";
    newAnnotationCreatedBy.value = "web-user";
  },
});

function addAnnotation() {
  if (!props.sampleId || !newAnnotationLabel.value) return;
  createAnnotationMutation.mutate({
    sample_id: props.sampleId,
    label: newAnnotationLabel.value,
    created_by: newAnnotationCreatedBy.value || "web-user",
  });
}

// ---------------------------------------------------------------------------
// Replace image state
// ---------------------------------------------------------------------------
const replaceFileInputRef = ref<HTMLInputElement | null>(null);
const replaceFile = ref<File | null>(null);
const replacePreviewUrl = ref<string | null>(null);
const uploadingImage = ref(false);

function onReplaceFileChange(e: Event) {
  const target = e.target as HTMLInputElement;
  const file = target.files?.[0] ?? null;
  replaceFile.value = file;
  if (replacePreviewUrl.value) {
    URL.revokeObjectURL(replacePreviewUrl.value);
  }
  replacePreviewUrl.value = file ? URL.createObjectURL(file) : null;
}

async function doUpload() {
  if (!props.sampleId || !replaceFile.value) return;
  uploadingImage.value = true;
  try {
    await api.uploadSampleImage(props.sampleId, replaceFile.value);
    qc.invalidateQueries({ queryKey: ["sample", props.sampleId] });
    replaceFile.value = null;
    if (replacePreviewUrl.value) {
      URL.revokeObjectURL(replacePreviewUrl.value);
      replacePreviewUrl.value = null;
    }
    if (replaceFileInputRef.value) {
      replaceFileInputRef.value.value = "";
    }
  } finally {
    uploadingImage.value = false;
  }
}

// ---------------------------------------------------------------------------
// Find Similar state
// ---------------------------------------------------------------------------
const findSimilarLoading = ref(false);
const findSimilarError = ref<string | null>(null);
const findSimilarSearched = ref(false);
const similarNeighbors = ref<Array<{ sample_id: string; score: number; previewUri: string }>>([]);

async function doFindSimilar() {
  if (!props.sampleId) return;
  findSimilarLoading.value = true;
  findSimilarError.value = null;
  findSimilarSearched.value = true;
  try {
    const result: SimilarityResponse = await api.getSimilarity(props.datasetId, props.sampleId, 10);
    const neighbors = await Promise.all(
      result.neighbors.map(async (nb) => {
        try {
          const sample = await api.getSample(nb.sample_id);
          const previewUri = sample.image_uris.length > 0
            ? resolveImageUris(sample.image_uris)[0]
            : fallbackPlaceholder;
          return { sample_id: nb.sample_id, score: nb.score, previewUri };
        } catch {
          return { sample_id: nb.sample_id, score: nb.score, previewUri: fallbackPlaceholder };
        }
      })
    );
    similarNeighbors.value = neighbors;
  } catch (e) {
    findSimilarError.value = e instanceof Error ? e.message : "Failed to find similar samples";
  } finally {
    findSimilarLoading.value = false;
  }
}

// ---------------------------------------------------------------------------
// Date formatter
// ---------------------------------------------------------------------------
function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

// ---------------------------------------------------------------------------
// Watcher: reset local state when sampleId changes
// ---------------------------------------------------------------------------
watch(
  () => props.sampleId,
  () => {
    editingAnnotationId.value = null;
    editingLabel.value = "";
    newAnnotationLabel.value = "";
    newAnnotationCreatedBy.value = "web-user";
    replaceFile.value = null;
    if (replacePreviewUrl.value) {
      URL.revokeObjectURL(replacePreviewUrl.value);
      replacePreviewUrl.value = null;
    }
    if (replaceFileInputRef.value) {
      replaceFileInputRef.value.value = "";
    }
    // Reset find-similar state
    findSimilarLoading.value = false;
    findSimilarError.value = null;
    findSimilarSearched.value = false;
    similarNeighbors.value = [];
  }
);
</script>
