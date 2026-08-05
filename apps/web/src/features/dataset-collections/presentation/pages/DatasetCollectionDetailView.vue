<script setup lang="ts">
import { computed, h, ref } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useRoute, useRouter } from "vue-router";
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NDescriptions,
  NDescriptionsItem,
  NEmpty,
  NModal,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NText,
  useMessage,
  type DataTableColumns,
} from "naive-ui";
import {
  createRevisionApiV1DatasetCollectionsCollectionIdRevisionsPost,
  getCollectionApiV1DatasetCollectionsCollectionIdGet,
  linkMembersApiV1DatasetCollectionsCollectionIdMembersPost,
  listDatasetsApiV1DatasetsGet,
  listMembersApiV1DatasetCollectionsCollectionIdMembersGet,
  listRevisionsApiV1DatasetCollectionsCollectionIdRevisionsGet,
  unlinkMemberApiV1DatasetCollectionsCollectionIdMembersMemberIdDelete,
} from "@/generated/orval/endpoints/api";
import type {
  Dataset,
  DatasetCollectionMemberResponse,
  DatasetCollectionRevisionResponse,
} from "@/generated/orval/models";
import { toUserMessage } from "@/shared/api";

const route = useRoute();
const router = useRouter();
const queryClient = useQueryClient();
const message = useMessage();
const collectionId = computed(() => String(route.params.collectionId));
const linkVisible = ref(false);
const selectedDatasetIds = ref<string[]>([]);

async function loadAllDatasets(): Promise<Dataset[]> {
  const datasets: Dataset[] = [];
  while (true) {
    const page = await listDatasetsApiV1DatasetsGet({ offset: datasets.length, limit: 200 });
    datasets.push(...page.items);
    if (datasets.length >= page.total || page.items.length === 0) return datasets;
  }
}

const collectionQuery = useQuery({
  queryKey: computed(() => ["dataset-collections", collectionId.value]),
  queryFn: () => getCollectionApiV1DatasetCollectionsCollectionIdGet(collectionId.value),
});
const membersQuery = useQuery({
  queryKey: computed(() => ["dataset-collections", collectionId.value, "members"]),
  queryFn: () => listMembersApiV1DatasetCollectionsCollectionIdMembersGet(collectionId.value),
});
const revisionsQuery = useQuery({
  queryKey: computed(() => ["dataset-collections", collectionId.value, "revisions"]),
  queryFn: () => listRevisionsApiV1DatasetCollectionsCollectionIdRevisionsGet(collectionId.value),
});
const datasetsQuery = useQuery({ queryKey: ["datasets", "all"], queryFn: loadAllDatasets });
const collection = computed(() => collectionQuery.data.value);
const members = computed(() =>
  [...(membersQuery.data.value ?? [])].sort((a, b) => a.position - b.position),
);
const datasets = computed(() => datasetsQuery.data.value ?? []);
const datasetById = computed(
  () => new Map(datasets.value.map((dataset) => [String(dataset.id ?? ""), dataset])),
);
const latestReadyRevision = computed(
  () =>
    [...(revisionsQuery.data.value ?? [])]
      .filter((revision) => revision.status === "ready")
      .sort((a, b) => b.revision_number - a.revision_number)[0],
);

async function refreshCollection(): Promise<void> {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ["dataset-collections", collectionId.value] }),
    queryClient.invalidateQueries({
      queryKey: ["dataset-collections", collectionId.value, "members"],
    }),
    queryClient.invalidateQueries({
      queryKey: ["dataset-collections", collectionId.value, "revisions"],
    }),
  ]);
}

const linkOptions = computed(() => {
  const linked = new Set(members.value.map((member) => member.source_dataset_id));
  const target = collection.value?.target_view_id;
  return datasets.value
    .filter(
      (dataset) =>
        !linked.has(String(dataset.id ?? "")) &&
        !!target &&
        (dataset.view_types ?? []).includes(target),
    )
    .map((dataset) => ({ label: dataset.name, value: String(dataset.id ?? "") }))
    .filter((option) => option.value.length > 0);
});

const linkMutation = useMutation({
  mutationFn: () => {
    const version = collection.value?.definition_version;
    if (version === undefined) throw new Error("Collection definition is not loaded");
    return linkMembersApiV1DatasetCollectionsCollectionIdMembersPost(collectionId.value, {
      expected_definition_version: version,
      members: selectedDatasetIds.value.map((sourceDatasetId, offset) => ({
        source_dataset_id: sourceDatasetId,
        position: members.value.length + offset,
        filter_spec: {},
        label_mapping: {},
        sampling_spec: {},
      })),
    });
  },
  onSuccess: async () => {
    message.success("Datasets linked");
    linkVisible.value = false;
    selectedDatasetIds.value = [];
    await refreshCollection();
  },
  onError: (error) => message.error(toUserMessage(error, "Failed to link datasets")),
});

const unlinkMutation = useMutation({
  mutationFn: (member: DatasetCollectionMemberResponse) => {
    const version = collection.value?.definition_version;
    if (version === undefined) throw new Error("Collection definition is not loaded");
    return unlinkMemberApiV1DatasetCollectionsCollectionIdMembersMemberIdDelete(
      collectionId.value,
      member.id,
      { expected_definition_version: version },
    );
  },
  onSuccess: async () => {
    message.success("Dataset unlinked");
    await refreshCollection();
  },
  onError: (error) => message.error(toUserMessage(error, "Failed to unlink dataset")),
});

const revisionMutation = useMutation({
  mutationFn: () => {
    const version = collection.value?.definition_version;
    if (version === undefined) throw new Error("Collection definition is not loaded");
    return createRevisionApiV1DatasetCollectionsCollectionIdRevisionsPost(collectionId.value, {
      expected_definition_version: version,
    });
  },
  onSuccess: async () => {
    message.success("Immutable collection revision created");
    await refreshCollection();
  },
  onError: (error) => message.error(toUserMessage(error, "Failed to create revision")),
});

function openStack(): void {
  const first = members.value[0];
  const revision = latestReadyRevision.value;
  if (!first || !revision) return;
  void router.push({
    path: `/dataset-collections/${collectionId.value}/classify/${first.source_dataset_id}`,
    query: { revisionId: revision.id },
  });
}

const memberColumns: DataTableColumns<DatasetCollectionMemberResponse> = [
  { title: "Order", key: "position", width: 80 },
  {
    title: "Dataset",
    key: "source_dataset_id",
    render: (row) => datasetById.value.get(row.source_dataset_id)?.name ?? row.source_dataset_id,
  },
  {
    title: "Linked in",
    key: "linked_definition_version",
    render: (row) => `definition v${row.linked_definition_version}`,
  },
  {
    title: "Actions",
    key: "actions",
    render: (row) =>
      h(NSpace, null, {
        default: () => [
          h(
            NButton,
            { size: "small", onClick: () => router.push(`/datasets/${row.source_dataset_id}`) },
            { default: () => "Open standalone" },
          ),
          h(
            NButton,
            {
              size: "small",
              type: "error",
              ghost: true,
              loading: unlinkMutation.isPending.value,
              onClick: () => unlinkMutation.mutate(row),
            },
            { default: () => "Unlink" },
          ),
        ],
      }),
  },
];

const revisionColumns: DataTableColumns<DatasetCollectionRevisionResponse> = [
  { title: "Revision", key: "revision_number", render: (row) => `r${row.revision_number}` },
  { title: "Definition", key: "definition_version", render: (row) => `v${row.definition_version}` },
  {
    title: "Status",
    key: "status",
    render: (row) =>
      h(
        NTag,
        { type: row.status === "ready" ? "success" : "error" },
        { default: () => row.status },
      ),
  },
  { title: "Rows", key: "row_count", render: (row) => row.row_count?.toLocaleString() ?? "—" },
  {
    title: "Created",
    key: "created_at",
    render: (row) => new Date(row.created_at).toLocaleString(),
  },
];
</script>

<template>
  <div class="collection-detail-page">
    <div class="collection-detail-header">
      <div>
        <NButton text size="small" @click="router.push('/dataset-collections')"
          >← Collections</NButton
        >
        <h1>{{ collection?.name ?? "Dataset collection" }}</h1>
        <NText depth="3">{{ collection?.description }}</NText>
      </div>
      <NSpace>
        <NButton
          :disabled="members.length === 0"
          :loading="revisionMutation.isPending.value"
          @click="revisionMutation.mutate()"
        >
          Create revision
        </NButton>
        <NButton
          type="primary"
          :disabled="!latestReadyRevision || members.length === 0"
          @click="openStack"
        >
          Open collection classify
        </NButton>
      </NSpace>
    </div>

    <NSpin v-if="collectionQuery.isLoading.value" />
    <template v-else-if="collection">
      <NAlert
        v-if="latestReadyRevision?.definition_version !== collection.definition_version"
        type="warning"
      >
        Membership has changed since the latest ready revision. Create a new revision before
        training or predicting the current composition.
      </NAlert>
      <NDescriptions bordered :column="3">
        <NDescriptionsItem label="Target view">{{ collection.target_view_id }}</NDescriptionsItem>
        <NDescriptionsItem label="Definition"
          >v{{ collection.definition_version }}</NDescriptionsItem
        >
        <NDescriptionsItem label="Members">{{ members.length }}</NDescriptionsItem>
      </NDescriptions>

      <NCard title="Linked datasets">
        <template #header-extra>
          <NButton type="primary" size="small" @click="linkVisible = true">Link datasets</NButton>
        </template>
        <NDataTable
          v-if="members.length > 0"
          :columns="memberColumns"
          :data="members"
          :row-key="(row: DatasetCollectionMemberResponse) => row.id"
        />
        <NEmpty v-else description="No datasets linked" />
      </NCard>

      <NCard title="Immutable revisions">
        <NDataTable
          v-if="(revisionsQuery.data.value ?? []).length > 0"
          :columns="revisionColumns"
          :data="revisionsQuery.data.value ?? []"
          :row-key="(row: DatasetCollectionRevisionResponse) => row.id"
        />
        <NEmpty v-else description="Create a revision to train or predict this composition" />
      </NCard>
    </template>

    <NModal
      v-model:show="linkVisible"
      preset="card"
      title="Link existing datasets"
      :style="{ width: '560px' }"
    >
      <NSelect
        v-model:value="selectedDatasetIds"
        multiple
        filterable
        :options="linkOptions"
        placeholder="Select compatible datasets"
      />
      <template #footer>
        <NSpace justify="end">
          <NButton @click="linkVisible = false">Cancel</NButton>
          <NButton
            type="primary"
            :disabled="selectedDatasetIds.length === 0"
            :loading="linkMutation.isPending.value"
            @click="linkMutation.mutate()"
          >
            Link
          </NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.collection-detail-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.collection-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

h1 {
  margin: 6px 0 3px;
  font-size: 24px;
}
</style>
