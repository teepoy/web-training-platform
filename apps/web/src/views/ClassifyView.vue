<template>
  <div class="classify-view" :style="themeStyleVars">
    <!-- Header bar -->
    <div class="classify-header">
      <n-button text @click="router.push(`/datasets/${datasetId}`)">
        <template #icon>
          <span>&#8592;</span>
        </template>
        Back
      </n-button>
      <n-divider vertical />
      <n-text tag="h2" style="margin: 0; font-size: 18px; font-weight: 600">
        {{ datasetQuery.data.value?.name ?? datasetId }}
      </n-text>
      <div
        style="margin-left: auto; display: flex; align-items: center; gap: 12px"
      >
        <n-text depth="3" style="white-space: nowrap">Image size</n-text>
        <n-slider
          v-model:value="thumbSize"
          :min="64"
          :max="256"
          :step="8"
          style="width: 160px"
        />
        <n-text depth="3" style="white-space: nowrap">{{ thumbSize }}px</n-text>
      </div>
    </div>

    <!-- Body: grid + sidebar -->
    <div class="classify-body">
      <AnnotationGrid
        ref="gridRef"
        :items="gridItems"
        :total-count="totalCount"
        :label-space="labelSpace"
        :thumb-size="thumbSize"
        :is-loading="isLoading"
        :submitting="bulkAnnotateMutation.isPending.value"
        :show-add-label="true"
        @select="onGridSelect"
        @apply-label="onGridApplyLabel"
        @submit="submitAnnotations"
        @load-more="loadMore"
        @add-label="showAddLabelModal = true"
      >
        <template #bar-left>
          <n-select
            v-model:value="labelFilter"
            :options="filterOptions"
            placeholder="Filter by label"
            size="tiny"
            clearable
            style="width: 160px"
          />
          <n-select
            v-model:value="orderBy"
            :options="orderOptions"
            size="tiny"
            style="width: 130px"
          />
        </template>
      </AnnotationGrid>

      <!-- Sidebar -->
      <ClassifySidebar
        :panels="mergedPanels"
        :context="dashboardContext"
        :interaction="sidebarInteraction"
        v-model:collapsed="sidebarCollapsed"
      />
    </div>

    <!-- Add Label Modal -->
    <n-modal
      v-model:show="showAddLabelModal"
      preset="dialog"
      title="Add New Label"
    >
      <n-input
        v-model:value="newLabelName"
        placeholder="Enter label name"
        @keyup.enter="addNewLabel"
      />
      <template #action>
        <n-button @click="showAddLabelModal = false">Cancel</n-button>
        <n-button
          type="primary"
          :loading="addLabelMutation.isPending.value"
          :disabled="!newLabelName.trim()"
          @click="addNewLabel"
        >
          Add
        </n-button>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/vue-query";
import {
  NButton,
  NText,
  NSlider,
  NDivider,
  NSelect,
  NModal,
  NInput,
  useMessage,
  useDialog,
  useThemeVars,
} from "naive-ui";
import { api, bulkCreateAnnotations, syncAnnotationsToLs } from "../api";
import type {
  SampleWithLabels,
  BulkAnnotationRequest,
  BulkAnnotationResponse,
  SyncResult,
  Dataset,
  AnnotationGridItem,
} from "../types";
import { resolveImageUris } from "../utils/imageAdapters";
import { useSampleLoader } from "../composables/useSampleLoader";
import AnnotationGrid from "../components/annotation/AnnotationGrid.vue";
import ClassifySidebar from "../components/classify/ClassifySidebar.vue";
import {
  defaultPanels,
  mergePanels,
} from "../components/classify/sidebarConfig";
import {
  reduceLabelFilterIntent,
  type SidebarWidgetIntent,
  type SidebarWidgetInteractionContext,
} from "../components/classify/widgetContract";
import { useClassifyDashboard } from "../composables/useClassifyDashboard";
import { GLOBAL_AGENT_PANELS_KEY } from "../composables/useGlobalAgent";

const route = useRoute();
const router = useRouter();
const datasetId = route.params.id as string;
const message = useMessage();
const dialog = useDialog();
const themeVars = useThemeVars();
const queryClient = useQueryClient();

const themeStyleVars = computed(() => ({
  "--cv-bg": themeVars.value.bodyColor,
  "--cv-card-bg": themeVars.value.cardColor,
  "--cv-text": themeVars.value.textColor1,
  "--cv-text-secondary": themeVars.value.textColor3,
  "--cv-text-disabled": themeVars.value.textColorDisabled,
  "--cv-border": themeVars.value.borderColor,
  "--cv-divider": themeVars.value.dividerColor,
  "--cv-hover": themeVars.value.hoverColor,
  "--cv-primary": themeVars.value.primaryColor,
  "--cv-primary-hover": themeVars.value.primaryColorHover,
}));

// ---------------------------------------------------------------------------
// Dataset query
// ---------------------------------------------------------------------------

const datasetQuery = useQuery({
  queryKey: ["dataset", datasetId],
  queryFn: () => api.getDataset(datasetId),
  retry: false,
});

const labelSpace = computed<string[]>(
  () => datasetQuery.data.value?.task_spec?.label_space ?? [],
);

// ---------------------------------------------------------------------------
// Sample loading
// ---------------------------------------------------------------------------

const thumbSize = ref(128);
const labelFilter = ref<string | null>(null);
const orderBy = ref<string>("id");

const filterOptions = computed(
  () =>
    [
      { label: "All", value: null as string | null },
      { label: "Unlabeled", value: "__unlabeled__" as string | null },
      ...labelSpace.value.map((l) => ({ label: l, value: l as string | null })),
    ] as any,
);

const orderOptions = [
  { label: "Default (id)", value: "id" },
  { label: "By Label", value: "label" },
  { label: "Newest First", value: "created_at" },
] as any;

const {
  samples,
  totalCount,
  isLoading,
  loadMore,
  reset: resetLoader,
} = useSampleLoader({
  datasetId,
  pageSize: 100,
  labelFilter,
  orderBy,
});

onMounted(() => {
  resetLoader();
});

// ---------------------------------------------------------------------------
// Draft labels
// ---------------------------------------------------------------------------

const labelDraft = ref<Record<string, string>>({});
const gridRef = ref<InstanceType<typeof AnnotationGrid> | null>(null);

const draftCount = computed(
  () => Object.keys(labelDraft.value).filter((k) => labelDraft.value[k]).length,
);

// ---------------------------------------------------------------------------
// Grid items (map SampleWithLabels → AnnotationGridItem)
// ---------------------------------------------------------------------------

const gridItems = computed<AnnotationGridItem[]>(() =>
  samples.value.map((s) => ({
    id: s.id,
    imageSrcs: resolveImageUris(s.image_uris ?? []),
    currentLabel: s.latest_annotation?.label ?? null,
    draftLabel: labelDraft.value[s.id] ?? null,
    predictionLabel: null,
    predictionConfidence: null,
    predictionId: null,
    metadata: s.metadata ?? {},
  })),
);

// ---------------------------------------------------------------------------
// Grid event handlers
// ---------------------------------------------------------------------------

const selectedCount = ref(0);

function onGridSelect(ids: Set<string>) {
  selectedCount.value = ids.size;
}

function onGridApplyLabel(payload: { ids: string[]; label: string }) {
  const draft = { ...labelDraft.value };
  payload.ids.forEach((id) => {
    draft[id] = payload.label;
  });
  labelDraft.value = draft;
}

watch(labelFilter, () => {
  selectedCount.value = 0;
  gridRef.value?.clearSelection();
});

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

const sidebarCollapsed = ref(false);

const dashboardContext = useClassifyDashboard(
  datasetId,
  draftCount,
  selectedCount,
  labelSpace,
);

// Inject agent panels from the global agent (provided in App.vue)
const globalAgentPanels = inject(GLOBAL_AGENT_PANELS_KEY, ref([]));

const mergedPanels = computed(() =>
  mergePanels(defaultPanels, globalAgentPanels.value),
);

function handleSidebarIntent(intent: SidebarWidgetIntent): void {
  labelFilter.value = reduceLabelFilterIntent(labelFilter.value, intent);
}

const sidebarInteraction = computed<SidebarWidgetInteractionContext>(() => ({
  state: {
    activeLabelFilter: labelFilter.value,
    selectedLabels: labelFilter.value ? [labelFilter.value] : [],
  },
  dispatch: handleSidebarIntent,
}));

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

const syncToLsMutation = useMutation({
  mutationFn: () => syncAnnotationsToLs(datasetId),
  onSuccess: (data: SyncResult) => {
    message.success(`Synced ${data.synced_count} annotations to Label Studio`);
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to sync to Label Studio");
  },
});

const bulkAnnotateMutation = useMutation({
  mutationFn: (body: BulkAnnotationRequest) =>
    bulkCreateAnnotations(datasetId, body),
  onSuccess: (data: BulkAnnotationResponse) => {
    message.success(`Created ${data.created} annotations`);
    if (datasetQuery.data.value?.ls_project_id) {
      syncToLsMutation.mutate();
    }
    labelDraft.value = {};
    gridRef.value?.clearSelection();
    resetLoader();
    queryClient.invalidateQueries({
      queryKey: ["annotation-stats", datasetId],
    });
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to create annotations");
  },
});

function submitAnnotations() {
  const entries = Object.entries(labelDraft.value).filter(([, label]) => label);
  if (entries.length === 0) {
    message.warning("No annotations to submit");
    return;
  }
  dialog.warning({
    title: "Submit annotations?",
    content: `This will create ${entries.length} annotation(s). Continue?`,
    positiveText: "Submit",
    negativeText: "Cancel",
    onPositiveClick: () => {
      bulkAnnotateMutation.mutate({
        annotations: entries.map(([sample_id, label]) => ({
          sample_id,
          label,
          annotator: "platform-user",
        })),
      });
    },
  });
}

// ---------------------------------------------------------------------------
// Add Label
// ---------------------------------------------------------------------------

const showAddLabelModal = ref(false);
const newLabelName = ref("");

const addLabelMutation = useMutation({
  mutationFn: (newLabel: string) => {
    const currentLabels = labelSpace.value;
    if (currentLabels.includes(newLabel)) {
      throw new Error(`Label "${newLabel}" already exists`);
    }
    return api.updateLabelSpace(datasetId, [...currentLabels, newLabel]);
  },
  onSuccess: () => {
    message.success(`Added label "${newLabelName.value}"`);
    showAddLabelModal.value = false;
    newLabelName.value = "";
    datasetQuery.refetch();
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to add label");
  },
});

function addNewLabel() {
  const trimmed = newLabelName.value.trim();
  if (!trimmed) return;
  addLabelMutation.mutate(trimmed);
}
</script>

<style scoped>
.classify-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding: 12px;
  box-sizing: border-box;
  color: var(--cv-text);
}

.classify-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-shrink: 0;
}

.classify-body {
  display: flex;
  flex: 1;
  min-height: 0;
  gap: 0;
}
</style>
