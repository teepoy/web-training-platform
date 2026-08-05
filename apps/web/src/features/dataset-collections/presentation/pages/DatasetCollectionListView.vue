<script setup lang="ts">
import { computed, h, ref, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useRouter } from "vue-router";
import {
  NButton,
  NCard,
  NDataTable,
  NEmpty,
  NFormItem,
  NInput,
  NModal,
  NSelect,
  NSpace,
  NTag,
  NText,
  useMessage,
  type DataTableColumns,
} from "naive-ui";
import {
  createCollectionApiV1DatasetCollectionsPost,
  linkMembersApiV1DatasetCollectionsCollectionIdMembersPost,
  listCollectionsApiV1DatasetCollectionsGet,
  listDatasetsApiV1DatasetsGet,
} from "@/generated/orval/endpoints/api";
import type { Dataset, DatasetCollectionResponse } from "@/generated/orval/models";
import { toUserMessage } from "@/shared/api";

const router = useRouter();
const queryClient = useQueryClient();
const message = useMessage();
const createVisible = ref(false);
const name = ref("");
const description = ref("");
const targetViewId = ref<string | null>(null);
const selectedDatasetIds = ref<string[]>([]);

async function loadAllDatasets(): Promise<Dataset[]> {
  const datasets: Dataset[] = [];
  while (true) {
    const page = await listDatasetsApiV1DatasetsGet({ offset: datasets.length, limit: 200 });
    datasets.push(...page.items);
    if (datasets.length >= page.total || page.items.length === 0) return datasets;
  }
}

const collectionsQuery = useQuery({
  queryKey: ["dataset-collections"],
  queryFn: () => listCollectionsApiV1DatasetCollectionsGet({ offset: 0, limit: 200 }),
});
const datasetsQuery = useQuery({ queryKey: ["datasets", "all"], queryFn: loadAllDatasets });
const collections = computed(() => collectionsQuery.data.value?.items ?? []);
const datasets = computed(() => datasetsQuery.data.value ?? []);

const targetViewOptions = computed(() => {
  const selected = datasets.value.filter((dataset) =>
    selectedDatasetIds.value.includes(String(dataset.id ?? "")),
  );
  const source = selected.length > 0 ? selected : datasets.value;
  const intersection = source.reduce<Set<string> | null>((result, dataset) => {
    const views = new Set(dataset.view_types ?? []);
    return result === null ? views : new Set([...result].filter((view) => views.has(view)));
  }, null);
  return [...(intersection ?? new Set<string>())].sort().map((view) => ({
    label: view,
    value: view,
  }));
});

watch(targetViewOptions, (options) => {
  if (targetViewId.value && options.some((option) => option.value === targetViewId.value)) return;
  targetViewId.value = null;
});

const datasetOptions = computed(() =>
  datasets.value
    .filter(
      (dataset) => !targetViewId.value || (dataset.view_types ?? []).includes(targetViewId.value),
    )
    .map((dataset) => ({
      label: dataset.name,
      value: String(dataset.id ?? ""),
    }))
    .filter((option) => option.value.length > 0),
);

const createMutation = useMutation({
  mutationFn: async () => {
    const collection = await createCollectionApiV1DatasetCollectionsPost({
      name: name.value.trim(),
      description: description.value.trim(),
      target_view_id: targetViewId.value ?? "",
      duplicate_policy: "keep_all",
      missing_data_policy: "fail",
    });
    if (selectedDatasetIds.value.length > 0) {
      await linkMembersApiV1DatasetCollectionsCollectionIdMembersPost(collection.id, {
        expected_definition_version: collection.definition_version,
        members: selectedDatasetIds.value.map((sourceDatasetId, position) => ({
          source_dataset_id: sourceDatasetId,
          position,
          filter_spec: {},
          label_mapping: {},
          sampling_spec: {},
        })),
      });
    }
    return collection;
  },
  onSuccess: async (collection) => {
    message.success("Dataset collection created");
    createVisible.value = false;
    await queryClient.invalidateQueries({ queryKey: ["dataset-collections"] });
    await router.push(`/dataset-collections/${collection.id}`);
  },
  onError: (error) => message.error(toUserMessage(error, "Failed to create collection")),
});

const canCreate = computed(() => name.value.trim().length > 0 && !!targetViewId.value);

function openCreate(): void {
  name.value = "";
  description.value = "";
  targetViewId.value = null;
  selectedDatasetIds.value = [];
  createVisible.value = true;
}

const columns: DataTableColumns<DatasetCollectionResponse> = [
  { title: "Name", key: "name" },
  { title: "Target view", key: "target_view_id" },
  {
    title: "Definition",
    key: "definition_version",
    render: (row) => `v${row.definition_version}`,
  },
  {
    title: "Policy",
    key: "duplicate_policy",
    render: () => h(NTag, { size: "small" }, { default: () => "Keep all samples" }),
  },
  {
    title: "Updated",
    key: "updated_at",
    render: (row) => new Date(row.updated_at).toLocaleString(),
  },
  {
    title: "",
    key: "actions",
    render: (row) =>
      h(
        NButton,
        { size: "small", onClick: () => router.push(`/dataset-collections/${row.id}`) },
        { default: () => "Open" },
      ),
  },
];
</script>

<template>
  <div class="collection-list-page">
    <div class="collection-list-header">
      <div>
        <h1>Dataset Collections</h1>
        <NText depth="3">Dynamically compose existing datasets without changing them.</NText>
      </div>
      <NButton type="primary" @click="openCreate">New collection</NButton>
    </div>

    <NCard>
      <NDataTable
        v-if="collections.length > 0"
        :columns="columns"
        :data="collections"
        :loading="collectionsQuery.isLoading.value"
        :row-key="(row: DatasetCollectionResponse) => row.id"
      />
      <NEmpty v-else-if="!collectionsQuery.isLoading.value" description="No collections yet">
        <template #extra>
          <NButton @click="openCreate">Create a collection</NButton>
        </template>
      </NEmpty>
    </NCard>

    <NModal
      v-model:show="createVisible"
      preset="card"
      title="Create dataset collection"
      :style="{ width: '620px' }"
    >
      <NFormItem label="Name" required>
        <NInput v-model:value="name" placeholder="Collection name" maxlength="255" />
      </NFormItem>
      <NFormItem label="Description">
        <NInput v-model:value="description" type="textarea" placeholder="Purpose and scope" />
      </NFormItem>
      <NFormItem label="Existing datasets">
        <NSelect
          v-model:value="selectedDatasetIds"
          multiple
          filterable
          clearable
          :options="datasetOptions"
          :loading="datasetsQuery.isLoading.value"
          placeholder="Select datasets to link now, or leave empty"
        />
      </NFormItem>
      <NFormItem label="Target view" required>
        <NSelect
          v-model:value="targetViewId"
          :options="targetViewOptions"
          placeholder="Choose a view supported by every selected dataset"
        />
      </NFormItem>
      <NText depth="3">
        Linked datasets remain standalone. Membership changes create a new definition version;
        training and prediction use an immutable revision.
      </NText>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="createVisible = false">Cancel</NButton>
          <NButton
            type="primary"
            :disabled="!canCreate"
            :loading="createMutation.isPending.value"
            @click="createMutation.mutate()"
          >
            Create
          </NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.collection-list-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.collection-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

h1 {
  margin: 0 0 4px;
  font-size: 24px;
}
</style>
