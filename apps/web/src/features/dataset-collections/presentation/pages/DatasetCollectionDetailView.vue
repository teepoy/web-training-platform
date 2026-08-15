<script setup lang="ts">
import { computed, h, ref } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useRoute, useRouter } from "vue-router";
import {
  NAlert,
  NButton,
  NCard,
  NDataTable,
  NEmpty,
  NModal,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NText,
  NTooltip,
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
import { useAuthStore } from "@/features/auth/application/store";
import { useOrgStore } from "@/features/auth/application/org";
import { orgScopedQueryKey, toUserMessage } from "@/shared/api";

const route = useRoute();
const router = useRouter();
const queryClient = useQueryClient();
const message = useMessage();
const authStore = useAuthStore();
const orgStore = useOrgStore();
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
  queryKey: computed(() =>
    orgScopedQueryKey(orgStore.currentOrgId, ["dataset-collections", collectionId.value]),
  ),
  queryFn: () => getCollectionApiV1DatasetCollectionsCollectionIdGet(collectionId.value),
  enabled: computed(() => !!orgStore.currentOrgId && !!collectionId.value),
});
const membersQuery = useQuery({
  queryKey: computed(() =>
    orgScopedQueryKey(orgStore.currentOrgId, [
      "dataset-collections",
      collectionId.value,
      "members",
    ]),
  ),
  queryFn: () => listMembersApiV1DatasetCollectionsCollectionIdMembersGet(collectionId.value),
  enabled: computed(() => !!orgStore.currentOrgId && !!collectionId.value),
});
const revisionsQuery = useQuery({
  queryKey: computed(() =>
    orgScopedQueryKey(orgStore.currentOrgId, [
      "dataset-collections",
      collectionId.value,
      "revisions",
    ]),
  ),
  queryFn: () => listRevisionsApiV1DatasetCollectionsCollectionIdRevisionsGet(collectionId.value),
  enabled: computed(() => !!orgStore.currentOrgId && !!collectionId.value),
});
const datasetsQuery = useQuery({
  queryKey: computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["datasets", "all"])),
  queryFn: loadAllDatasets,
  enabled: computed(() => !!orgStore.currentOrgId),
});
const collection = computed(() => collectionQuery.data.value);
const canModify = computed(
  () => !!collection.value && collection.value.created_by === authStore.user?.id,
);
const loadError = computed(
  () =>
    collectionQuery.error.value ?? membersQuery.error.value ?? revisionsQuery.error.value ?? null,
);
const isLoading = computed(
  () =>
    collectionQuery.isLoading.value ||
    membersQuery.isLoading.value ||
    revisionsQuery.isLoading.value,
);
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
const revisionOutdated = computed(
  () =>
    !latestReadyRevision.value ||
    latestReadyRevision.value.definition_version !== collection.value?.definition_version,
);

async function refreshCollection(): Promise<void> {
  const key = (...parts: string[]) =>
    orgScopedQueryKey(orgStore.currentOrgId, ["dataset-collections", collectionId.value, ...parts]);
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: key() }),
    queryClient.invalidateQueries({ queryKey: key("members") }),
    queryClient.invalidateQueries({ queryKey: key("revisions") }),
  ]);
}

function labelSpacesMatch(first: Dataset | undefined, second: Dataset): boolean {
  if (!first) return true;
  const expected = first.task_spec?.label_space ?? [];
  const actual = second.task_spec?.label_space ?? [];
  return (
    actual.length === expected.length && actual.every((label, index) => label === expected[index])
  );
}

const selectedLinkDatasets = computed(() =>
  selectedDatasetIds.value
    .map((datasetId) => datasetById.value.get(datasetId))
    .filter((dataset): dataset is Dataset => !!dataset),
);
const memberLabelBaseline = computed(() => {
  const firstMember = members.value[0];
  return firstMember ? datasetById.value.get(firstMember.source_dataset_id) : undefined;
});
const selectedLinksCompatible = computed(() => {
  const baseline = memberLabelBaseline.value ?? selectedLinkDatasets.value[0];
  return selectedLinkDatasets.value.every((dataset) => labelSpacesMatch(baseline, dataset));
});

const linkOptions = computed(() => {
  const linked = new Set(members.value.map((member) => member.source_dataset_id));
  const target = collection.value?.target_view_id;
  return datasets.value
    .filter(
      (dataset) =>
        !linked.has(String(dataset.id ?? "")) &&
        !!target &&
        (dataset.view_types ?? []).includes(target) &&
        labelSpacesMatch(memberLabelBaseline.value ?? selectedLinkDatasets.value[0], dataset),
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
    message.success("Fixed snapshot created");
    await refreshCollection();
  },
  onError: (error) => message.error(toUserMessage(error, "Failed to create snapshot")),
});

function openStack(): void {
  const revision = latestReadyRevision.value;
  const firstSource = revision?.source_snapshot[0]?.source_dataset_id;
  if (!revision || typeof firstSource !== "string" || !firstSource) return;
  void router.push({
    path: `/dataset-collections/${collectionId.value}/classify/${firstSource}`,
    query: { revisionId: revision.id },
  });
}

const memberColumns: DataTableColumns<DatasetCollectionMemberResponse> = [
  { title: "Order", key: "position", width: 80 },
  {
    title: "Dataset",
    key: "source_dataset_id",
    minWidth: 180,
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
    width: 250,
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
              disabled: !canModify.value,
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
  {
    title: "Snapshot",
    key: "revision_number",
    render: (row) => `r${row.revision_number}`,
  },
  {
    title: "Saved from setup",
    key: "definition_version",
    render: (row) => `v${row.definition_version}`,
  },
  {
    title: "Status",
    key: "status",
    render: (row) =>
      h(
        NTag,
        { type: row.status === "ready" ? "success" : "error" },
        { default: () => (row.status === "ready" ? "Ready to use" : "Failed") },
      ),
  },
  { title: "Rows", key: "row_count", render: (row) => row.row_count?.toLocaleString() ?? "—" },
  {
    title: "Created",
    key: "created_at",
    width: 180,
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
      <NSpace class="collection-header-actions" :wrap="true">
        <NButton
          :disabled="members.length === 0 || !canModify"
          :loading="revisionMutation.isPending.value"
          :type="revisionOutdated ? 'primary' : 'default'"
          @click="revisionMutation.mutate()"
        >
          {{ latestReadyRevision ? "Save current setup as snapshot" : "Save first snapshot" }}
        </NButton>
        <NButton
          :type="revisionOutdated ? 'default' : 'primary'"
          :disabled="!latestReadyRevision"
          @click="openStack"
        >
          {{
            latestReadyRevision
              ? `Review snapshot r${latestReadyRevision.revision_number}`
              : "No snapshot to review"
          }}
        </NButton>
      </NSpace>
    </div>

    <div v-if="isLoading" class="collection-loading"><NSpin size="large" /></div>
    <NAlert v-else-if="loadError" type="error">
      {{ toUserMessage(loadError, "Failed to load dataset collection") }}
    </NAlert>
    <template v-else-if="collection">
      <NAlert v-if="!canModify" type="info">
        This collection is read-only for you. Only its creator can change membership or create
        snapshots.
      </NAlert>
      <NAlert type="info" :show-icon="false" class="snapshot-explainer">
        <strong>What is a revision?</strong>
        A revision is a fixed snapshot of the linked datasets and rules at one point in time.
        Review, training, and prediction use that snapshot so their input stays reproducible even if
        you change the collection later.
      </NAlert>
      <NAlert v-if="!latestReadyRevision" type="info">
        This collection does not have a saved snapshot yet. Save one before using it for review,
        training, or prediction.
      </NAlert>
      <NAlert v-else-if="revisionOutdated" type="warning">
        The collection setup has changed since the latest snapshot. Save a new snapshot to use the
        current setup. Review still opens snapshot r{{ latestReadyRevision.revision_number }}.
      </NAlert>
      <NCard size="small">
        <div class="collection-summary-grid">
          <div class="collection-summary-field">
            <NText depth="3">Target view</NText>
            <strong>{{ collection.target_view_id }}</strong>
          </div>
          <div class="collection-summary-field">
            <NTooltip>
              <template #trigger>
                <NText depth="3" class="help-label">Current setup version</NText>
              </template>
              Increases whenever linked datasets or their rules change.
            </NTooltip>
            <strong>v{{ collection.definition_version }}</strong>
          </div>
          <div class="collection-summary-field">
            <NText depth="3">Linked datasets</NText>
            <strong>{{ members.length }}</strong>
          </div>
          <div class="collection-summary-field">
            <NTooltip>
              <template #trigger>
                <NText depth="3" class="help-label">Latest fixed snapshot</NText>
              </template>
              The reproducible input used by review, training, and prediction.
            </NTooltip>
            <strong>{{
              latestReadyRevision ? `r${latestReadyRevision.revision_number}` : "None"
            }}</strong>
          </div>
        </div>
      </NCard>

      <NCard title="Linked datasets">
        <template #header-extra>
          <NButton type="primary" size="small" :disabled="!canModify" @click="linkVisible = true">
            Link datasets
          </NButton>
        </template>
        <NDataTable
          v-if="members.length > 0"
          :columns="memberColumns"
          :data="members"
          :row-key="(row: DatasetCollectionMemberResponse) => row.id"
          :scroll-x="760"
        />
        <NEmpty v-else description="No datasets linked" />
      </NCard>

      <NCard title="Saved snapshots (revisions)">
        <NDataTable
          v-if="(revisionsQuery.data.value ?? []).length > 0"
          :columns="revisionColumns"
          :data="revisionsQuery.data.value ?? []"
          :row-key="(row: DatasetCollectionRevisionResponse) => row.id"
          :scroll-x="640"
        />
        <NEmpty v-else description="Save a snapshot to train or predict this collection" />
      </NCard>
    </template>

    <NModal
      v-model:show="linkVisible"
      preset="card"
      title="Link existing datasets"
      :style="{ width: 'min(560px, calc(100vw - 32px))' }"
    >
      <template v-if="linkOptions.length > 0">
        <NSelect
          v-model:value="selectedDatasetIds"
          multiple
          filterable
          :options="linkOptions"
          placeholder="Select compatible datasets"
        />
        <NAlert v-if="!selectedLinksCompatible" type="error" :show-icon="false">
          Selected datasets must use the same labels in the same order.
        </NAlert>
      </template>
      <NEmpty
        v-else
        description="No unlinked datasets match this collection's view and label contract"
      />
      <template #footer>
        <NSpace justify="end">
          <NButton @click="linkVisible = false">Cancel</NButton>
          <NButton
            type="primary"
            :disabled="selectedDatasetIds.length === 0 || !selectedLinksCompatible"
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
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}

.collection-detail-header > div:first-child {
  min-width: 0;
}

.collection-detail-header h1,
.collection-detail-header :deep(.n-text) {
  overflow-wrap: anywhere;
}

.collection-header-actions {
  flex: 0 0 auto;
}

.collection-loading {
  display: flex;
  justify-content: center;
  padding: 56px;
}

.snapshot-explainer strong {
  margin-right: 6px;
}

.help-label {
  cursor: help;
  text-decoration: underline dotted;
  text-underline-offset: 3px;
}

.collection-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0;
}

.collection-summary-field {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
  padding: 0 20px;
  border-left: 1px solid var(--n-border-color, #e5e7eb);
}

.collection-summary-field:first-child {
  padding-left: 0;
  border-left: 0;
}

.collection-summary-field strong {
  overflow-wrap: anywhere;
  font-weight: 600;
}

h1 {
  margin: 6px 0 3px;
  font-size: 24px;
}

@media (max-width: 840px) {
  .collection-detail-header {
    align-items: stretch;
    flex-direction: column;
  }

  .collection-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 18px 0;
  }

  .collection-summary-field:nth-child(odd) {
    padding-left: 0;
    border-left: 0;
  }
}

@media (max-width: 520px) {
  .collection-header-actions {
    display: grid !important;
    grid-template-columns: 1fr;
  }

  .collection-header-actions :deep(.n-button) {
    width: 100%;
  }

  .collection-summary-grid {
    grid-template-columns: 1fr;
  }

  .collection-summary-field {
    padding: 0;
    border-left: 0;
  }
}
</style>
