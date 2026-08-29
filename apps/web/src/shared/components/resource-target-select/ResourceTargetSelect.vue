<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { refDebounced } from "@vueuse/core";
import { NAlert, NRadioButton, NRadioGroup, NSelect, NText } from "naive-ui";
import {
  useListCollectionsApiV1DatasetCollectionsGet,
  useListDatasetsApiV1DatasetsGet,
  useListRevisionsApiV1DatasetCollectionsCollectionIdRevisionsGet,
} from "@/generated/orval/endpoints/api";
import { useOrgStore } from "@/features/auth/application/org";
import { orgScopedQueryKey } from "@/shared/api";
import { latestReadyCollectionRevision, type ResourceTargetSelection } from "./types";

const props = withDefaults(
  defineProps<{
    modelValue: ResourceTargetSelection | null;
    active?: boolean;
  }>(),
  { active: true },
);

const emit = defineEmits<{
  (event: "update:modelValue", value: ResourceTargetSelection | null): void;
}>();

const orgStore = useOrgStore();
const resourceKind = ref<"dataset" | "collection">(props.modelValue?.kind ?? "dataset");
const selectedId = ref<string | null>(props.modelValue?.id ?? null);
const search = ref("");
const debouncedSearch = refDebounced(search, 250);

const datasetsQuery = useListDatasetsApiV1DatasetsGet(
  computed(() => ({
    q: debouncedSearch.value.trim() || undefined,
    limit: 50,
    offset: 0,
    sort_by: "created_at" as const,
    sort_order: "desc" as const,
  })),
  {
    query: {
      queryKey: computed(() =>
        orgScopedQueryKey(orgStore.currentOrgId, [
          "resource-targets",
          "datasets",
          debouncedSearch.value,
        ]),
      ),
      enabled: computed(
        () => props.active && resourceKind.value === "dataset" && !!orgStore.currentOrgId,
      ),
    },
  },
);

const collectionsQuery = useListCollectionsApiV1DatasetCollectionsGet(
  computed(() => ({
    q: debouncedSearch.value.trim() || undefined,
    limit: 50,
    offset: 0,
    sort_by: "updated_at" as const,
    sort_order: "desc" as const,
  })),
  {
    query: {
      queryKey: computed(() =>
        orgScopedQueryKey(orgStore.currentOrgId, [
          "resource-targets",
          "collections",
          debouncedSearch.value,
        ]),
      ),
      enabled: computed(
        () => props.active && resourceKind.value === "collection" && !!orgStore.currentOrgId,
      ),
    },
  },
);

const revisionsQuery = useListRevisionsApiV1DatasetCollectionsCollectionIdRevisionsGet(
  computed(() => (resourceKind.value === "collection" ? (selectedId.value ?? "") : "")),
  {
    query: {
      queryKey: computed(() =>
        orgScopedQueryKey(orgStore.currentOrgId, [
          "resource-targets",
          "collection-revisions",
          selectedId.value,
        ]),
      ),
      enabled: computed(
        () =>
          props.active &&
          resourceKind.value === "collection" &&
          !!selectedId.value &&
          !!orgStore.currentOrgId,
      ),
    },
  },
);

const datasetOptions = computed(() =>
  (datasetsQuery.data.value?.items ?? []).map((dataset) => ({
    label: dataset.name,
    value: dataset.id,
  })),
);
const collectionOptions = computed(() =>
  (collectionsQuery.data.value?.items ?? []).map((collection) => ({
    label: collection.name,
    value: collection.id,
  })),
);
const latestReadyRevision = computed(() =>
  latestReadyCollectionRevision(revisionsQuery.data.value ?? []),
);

watch(resourceKind, () => {
  selectedId.value = null;
  search.value = "";
  emit("update:modelValue", null);
});

watch(
  [
    resourceKind,
    selectedId,
    () => datasetsQuery.data.value,
    () => collectionsQuery.data.value,
    latestReadyRevision,
  ],
  () => {
    const id = selectedId.value;
    if (!id) {
      emit("update:modelValue", null);
      return;
    }
    if (resourceKind.value === "dataset") {
      const dataset = datasetsQuery.data.value?.items.find((item) => item.id === id);
      emit(
        "update:modelValue",
        dataset
          ? {
              kind: "dataset",
              id,
              name: dataset.name,
              viewTypes: dataset.view_types ?? [],
            }
          : null,
      );
      return;
    }
    const collection = collectionsQuery.data.value?.items.find((item) => item.id === id);
    const revision = latestReadyRevision.value;
    emit(
      "update:modelValue",
      collection && revision
        ? {
            kind: "collection",
            id: collection.id,
            name: collection.name,
            viewTypes: [revision.target_view_id],
            revisionId: revision.id,
            revisionNumber: revision.revision_number,
          }
        : null,
    );
  },
  { immediate: true },
);
</script>

<template>
  <div class="resource-target-select">
    <NRadioGroup v-model:value="resourceKind" name="resource-kind" size="small">
      <NRadioButton value="dataset">Dataset</NRadioButton>
      <NRadioButton value="collection">Collection</NRadioButton>
    </NRadioGroup>
    <NSelect
      v-model:value="selectedId"
      :options="resourceKind === 'dataset' ? datasetOptions : collectionOptions"
      :loading="
        resourceKind === 'dataset'
          ? datasetsQuery.isLoading.value
          : collectionsQuery.isLoading.value
      "
      :placeholder="resourceKind === 'dataset' ? 'Select a dataset' : 'Select a collection'"
      filterable
      remote
      clearable
      @search="search = $event"
    />
    <NText v-if="modelValue?.kind === 'collection'" depth="3">
      Snapshot r{{ modelValue.revisionNumber }} will be pinned for this run.
    </NText>
    <NAlert
      v-else-if="
        resourceKind === 'collection' &&
        selectedId &&
        !revisionsQuery.isLoading.value &&
        !latestReadyRevision
      "
      type="warning"
    >
      This collection has no ready snapshot. Create a ready revision before starting a run.
    </NAlert>
  </div>
</template>

<style scoped>
.resource-target-select {
  display: grid;
  gap: 10px;
}
</style>
