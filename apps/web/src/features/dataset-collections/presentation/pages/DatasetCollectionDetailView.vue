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
  NFormItem,
  NInput,
  NModal,
  NPopconfirm,
  NSelect,
  NSpace,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
  NText,
  NTooltip,
  useMessage,
  type DataTableColumns,
} from "naive-ui";
import {
  createRevisionApiV1DatasetCollectionsCollectionIdRevisionsPost,
  createMembershipRuleApiV1DatasetCollectionsCollectionIdMembershipRulesPost,
  getCollectionApiV1DatasetCollectionsCollectionIdGet,
  getModelApiV1ModelsModelIdGet,
  linkMembersApiV1DatasetCollectionsCollectionIdMembersPost,
  listDatasetsApiV1DatasetsGet,
  listMembershipRulesApiV1DatasetCollectionsCollectionIdMembershipRulesGet,
  listSourceConnectorsApiV1SourceConnectorsGet,
  listSourceProvidersApiV1SourceConnectorsProvidersGet,
  listImportProfilesApiV1SourceConnectorsConnectorIdImportProfilesGet,
  listMembersApiV1DatasetCollectionsCollectionIdMembersGet,
  listRevisionsApiV1DatasetCollectionsCollectionIdRevisionsGet,
  unlinkMemberApiV1DatasetCollectionsCollectionIdMembersMemberIdDelete,
  runMembershipDiscoveryApiV1DatasetCollectionsCollectionIdMembershipRulesRuleIdRunsPost,
} from "@/generated/orval/endpoints/api";
import type {
  Dataset,
  DatasetCollectionResponse,
  DatasetCollectionMemberResponse,
  DatasetCollectionRevisionResponse,
  CreateMembershipRuleRequest,
  FilterOperator,
  MembershipRuleResponse,
  SourceConnectorResponse,
  SourceProviderDescriptorResponse,
} from "@/generated/orval/models";
import {
  createCollectionPredictionBatch,
  listCollectionPredictionBatches,
  listCollectionPredictionCoverage,
  retryCollectionPredictionBatch,
  updateCollectionDefaultModel,
  type CollectionPredictionBatch,
  type CollectionPredictionCoverage,
  type CollectionWithDefaultModel,
} from "@/features/dataset-collections/api/collectionModelAutomation";
import {
  getCollectionSnapshotUpdateStatus,
  refreshCollectionSnapshot,
} from "@/features/dataset-collections/api/collectionSnapshotUpdates";
import CollectionSnapshotUpdateAlert from "@/features/dataset-collections/presentation/components/CollectionSnapshotUpdateAlert.vue";
import PredictionExportPlugin from "@/features/sc/presentation/components/PredictionExportPlugin.vue";
import { supportsScPredictionExport } from "@/features/sc/domain/predictionExportCapability";
import { useAuthStore } from "@/features/auth/application/store";
import { useOrgStore } from "@/features/auth/application/org";
import { orgScopedQueryKey, toUserMessage } from "@/shared/api";
import RemoteModelPicker from "@/features/models/presentation/components/RemoteModelPicker.vue";

const route = useRoute();
const router = useRouter();
const queryClient = useQueryClient();
const message = useMessage();
const authStore = useAuthStore();
const orgStore = useOrgStore();
const collectionId = computed(() => String(route.params.collectionId));
const activeTab = ref("overview");
const linkVisible = ref(false);
const selectedDatasetIds = ref<string[]>([]);
const modelVisible = ref(false);
const selectedDefaultModelId = ref<string | null>(null);
const reconcileVisible = ref(false);
const selectedCoverageMemberIds = ref<string[]>([]);
const exportVisible = ref(false);
const ruleVisible = ref(false);
const ruleName = ref("");
const ruleConnectorId = ref<string | null>(null);
const ruleProfileId = ref<string | null>(null);
const ruleField = ref<string | null>(null);
const ruleOperator = ref<FilterOperator | null>(null);
const ruleValue = ref("");

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
const snapshotUpdateQuery = useQuery({
  queryKey: computed(() =>
    orgScopedQueryKey(orgStore.currentOrgId, [
      "dataset-collections",
      collectionId.value,
      "snapshot-update-status",
    ]),
  ),
  queryFn: () => getCollectionSnapshotUpdateStatus(collectionId.value),
  enabled: computed(() => !!orgStore.currentOrgId && !!collectionId.value),
});
const datasetsQuery = useQuery({
  queryKey: computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["datasets", "all"])),
  queryFn: loadAllDatasets,
  enabled: computed(() => !!orgStore.currentOrgId),
});
const rulesQuery = useQuery({
  queryKey: computed(() =>
    orgScopedQueryKey(orgStore.currentOrgId, [
      "dataset-collections",
      collectionId.value,
      "membership-rules",
    ]),
  ),
  queryFn: () =>
    listMembershipRulesApiV1DatasetCollectionsCollectionIdMembershipRulesGet(collectionId.value),
  enabled: computed(() => !!orgStore.currentOrgId && !!collectionId.value),
});
const connectorsQuery = useQuery({
  queryKey: computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["source-connectors"])),
  queryFn: listSourceConnectorsApiV1SourceConnectorsGet,
  enabled: computed(() => !!orgStore.currentOrgId),
});
const providersQuery = useQuery({
  queryKey: computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["source-providers"])),
  queryFn: listSourceProvidersApiV1SourceConnectorsProvidersGet,
  enabled: computed(() => !!orgStore.currentOrgId),
});
const profilesQuery = useQuery({
  queryKey: computed(() =>
    orgScopedQueryKey(orgStore.currentOrgId, [
      "source-connectors",
      ruleConnectorId.value ?? "none",
      "import-profiles",
    ]),
  ),
  queryFn: () =>
    listImportProfilesApiV1SourceConnectorsConnectorIdImportProfilesGet(
      String(ruleConnectorId.value),
    ),
  enabled: computed(() => !!orgStore.currentOrgId && !!ruleConnectorId.value),
});
const collection = computed(
  () =>
    collectionQuery.data.value as
      | (DatasetCollectionResponse & CollectionWithDefaultModel)
      | undefined,
);
const isScCollection = computed(() => {
  const targetViewId = collection.value?.target_view_id;
  const targetContract = collection.value?.target_view_contract;
  return (
    targetViewId === "patch_image_v1" ||
    targetViewId === "sc:patch-image@v1" ||
    targetContract?.startsWith("sc.patch-image") === true
  );
});
const canModify = computed(
  () => !!collection.value && collection.value.created_by === authStore.user?.id,
);
const canManageAutomation = computed(
  () => !!collection.value && collection.value.org_id === orgStore.currentOrgId,
);
const loadError = computed(
  () =>
    collectionQuery.error.value ??
    membersQuery.error.value ??
    revisionsQuery.error.value ??
    snapshotUpdateQuery.error.value ??
    null,
);
const isLoading = computed(
  () =>
    collectionQuery.isLoading.value ||
    membersQuery.isLoading.value ||
    revisionsQuery.isLoading.value ||
    snapshotUpdateQuery.isLoading.value,
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
const coverageQuery = useQuery({
  queryKey: computed(() =>
    orgScopedQueryKey(orgStore.currentOrgId, [
      "dataset-collections",
      collectionId.value,
      "prediction-coverage",
      latestReadyRevision.value?.id ?? "none",
    ]),
  ),
  queryFn: () =>
    listCollectionPredictionCoverage(collectionId.value, String(latestReadyRevision.value?.id)),
  enabled: computed(
    () => !!orgStore.currentOrgId && !!collectionId.value && !!latestReadyRevision.value,
  ),
  refetchInterval: 5_000,
});
const batchesQuery = useQuery({
  queryKey: computed(() =>
    orgScopedQueryKey(orgStore.currentOrgId, [
      "dataset-collections",
      collectionId.value,
      "prediction-batches",
    ]),
  ),
  queryFn: () => listCollectionPredictionBatches(collectionId.value),
  enabled: computed(() => !!orgStore.currentOrgId && !!collectionId.value),
  refetchInterval: 5_000,
});
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
    queryClient.invalidateQueries({ queryKey: key("snapshot-update-status") }),
    queryClient.invalidateQueries({ queryKey: key("prediction-coverage") }),
    queryClient.invalidateQueries({ queryKey: key("prediction-batches") }),
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
    message.success("Snapshot record saved");
    await refreshCollection();
  },
  onError: (error) => message.error(toUserMessage(error, "Failed to create snapshot")),
});

const snapshotRefreshMutation = useMutation({
  mutationFn: () => {
    const version = collection.value?.definition_version;
    if (version === undefined) throw new Error("Collection definition is not loaded");
    return refreshCollectionSnapshot(collectionId.value, {
      expected_definition_version: version,
    });
  },
  onSuccess: async (result) => {
    message.success(
      result.outcome === "refreshed"
        ? `Snapshot #${result.snapshot.revision_number} now records the latest Dataset changes`
        : "Snapshot already records the latest Dataset changes",
    );
    await refreshCollection();
  },
  onError: (error) => message.error(toUserMessage(error, "Failed to refresh snapshot")),
});

const defaultModelQuery = useQuery({
  queryKey: computed(() =>
    orgScopedQueryKey(orgStore.currentOrgId, [
      "models",
      "collection-default",
      collection.value?.default_model_id ?? null,
    ]),
  ),
  queryFn: () => getModelApiV1ModelsModelIdGet(collection.value?.default_model_id ?? ""),
  enabled: computed(() => !!orgStore.currentOrgId && !!collection.value?.default_model_id),
});
const defaultModel = computed(() => defaultModelQuery.data.value);
const coverage = computed(() => coverageQuery.data.value ?? []);
const coverageByMemberId = computed(
  () => new Map(coverage.value.map((item) => [item.member_id, item])),
);
const needsPrediction = computed(() =>
  coverage.value.filter((item) => item.status !== "current" && !item.active_prediction_job_id),
);
const modelMismatchCount = computed(
  () => coverage.value.filter((item) => item.status === "model_mismatch").length,
);
const selectedCoverage = computed(() =>
  selectedCoverageMemberIds.value
    .map((memberId) => coverageByMemberId.value.get(memberId))
    .filter(
      (item): item is CollectionPredictionCoverage =>
        !!item && item.status !== "current" && !item.active_prediction_job_id,
    ),
);
const selectedMembers = computed(() => {
  const selected = new Set(selectedCoverageMemberIds.value);
  return members.value.filter((member) => selected.has(member.id));
});
const selectedMemberDatasetIds = computed(() =>
  selectedMembers.value.map((member) => member.source_dataset_id),
);
const selectedExportDatasets = computed(() =>
  selectedMemberDatasetIds.value
    .map((datasetId) => datasetById.value.get(datasetId))
    .filter((dataset): dataset is Dataset => !!dataset),
);
const exportDisabledReason = computed(() => {
  if (selectedMembers.value.length === 0) return "Select at least one linked Dataset record";
  if (
    selectedExportDatasets.value.length !== selectedMembers.value.length ||
    selectedExportDatasets.value.some((dataset) => !supportsScPredictionExport(dataset))
  ) {
    return "Current-result export requires SC Datasets using sparse storage";
  }
  return "";
});

function showModelPicker(): void {
  selectedDefaultModelId.value = collection.value?.default_model_id ?? null;
  modelVisible.value = true;
}

const defaultModelMutation = useMutation({
  mutationFn: (modelId: string | null) => {
    const bindingVersion = collection.value?.model_binding_version;
    if (bindingVersion === undefined) throw new Error("Default model setting is not loaded");
    return updateCollectionDefaultModel(collectionId.value, {
      expected_binding_version: bindingVersion,
      model_id: modelId,
    });
  },
  onSuccess: async () => {
    modelVisible.value = false;
    message.success(
      selectedDefaultModelId.value ? "Default model updated" : "Default model cleared",
    );
    await refreshCollection();
  },
  onError: (error) => message.error(toUserMessage(error, "Failed to update default model")),
});

const reconcileMutation = useMutation({
  mutationFn: () => {
    const snapshot = latestReadyRevision.value;
    const modelId = collection.value?.default_model_id;
    if (!snapshot || !modelId) throw new Error("Snapshot and default model are required");
    return createCollectionPredictionBatch(collectionId.value, {
      snapshot_id: snapshot.id,
      expected_default_model_id: modelId,
      request_id: crypto.randomUUID(),
      dataset_ids: selectedCoverage.value.map((item) => item.dataset_id),
    });
  },
  onSuccess: async () => {
    message.success("Prediction batch started");
    reconcileVisible.value = false;
    selectedCoverageMemberIds.value = [];
    await refreshCollection();
  },
  onError: (error) => message.error(toUserMessage(error, "Failed to start prediction batch")),
});

const retryBatchMutation = useMutation({
  mutationFn: (batchId: string) => retryCollectionPredictionBatch(collectionId.value, batchId),
  onSuccess: async () => {
    message.success("Failed datasets queued again");
    await refreshCollection();
  },
  onError: (error) => message.error(toUserMessage(error, "Failed to retry prediction batch")),
});

function coverageLabel(item: CollectionPredictionCoverage | undefined): string {
  if (!item) {
    if (!latestReadyRevision.value) return "No snapshot";
    if (coverageQuery.isLoading.value) return "Loading";
    if (coverageQuery.isError.value) return "Unavailable";
    return "Not evaluated";
  }
  if (item.active_prediction_status === "running") return "Prediction running";
  if (item.active_prediction_status === "queued") return "Prediction queued";
  if (item.status === "current") return "Current";
  if (item.status === "model_mismatch") return "Different model";
  if (item.status === "data_outdated") return "Dataset changed";
  return "Not predicted";
}

function coverageTagType(
  item: CollectionPredictionCoverage | undefined,
): "default" | "success" | "warning" | "error" | "info" {
  if (item?.active_prediction_job_id) return "info";
  if (item?.status === "current") return "success";
  if (item?.status === "model_mismatch") return "error";
  if (item?.status === "data_outdated") return "warning";
  return "default";
}

function openStack(): void {
  const revision = latestReadyRevision.value;
  const firstSource = revision?.source_snapshot[0]?.source_dataset_id;
  if (!revision || typeof firstSource !== "string" || !firstSource) return;
  void router.push({
    path: `/dataset-collections/${collectionId.value}/classify/${firstSource}`,
    query: { revisionId: revision.id },
  });
}

function handleTabBeforeLeave(name: string | number): boolean {
  if (name !== "classify") return true;
  if (!latestReadyRevision.value) return false;
  openStack();
  return false;
}

function closeExport(): void {
  exportVisible.value = false;
}

const memberColumns: DataTableColumns<DatasetCollectionMemberResponse> = [
  { type: "selection" },
  { title: "Order", key: "position", width: 80 },
  {
    title: "Dataset",
    key: "source_dataset_id",
    minWidth: 180,
    render: (row) => datasetById.value.get(row.source_dataset_id)?.name ?? row.source_dataset_id,
  },
  {
    title: "Prediction",
    key: "prediction",
    minWidth: 150,
    render: (row) => {
      const item = coverageByMemberId.value.get(row.id);
      return h(NTag, { type: coverageTagType(item) }, { default: () => coverageLabel(item) });
    },
  },
  {
    title: "Actions",
    key: "actions",
    width: 250,
    fixed: "right",
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

const batchColumns: DataTableColumns<CollectionPredictionBatch> = [
  {
    title: "Started",
    key: "created_at",
    width: 180,
    render: (row) => new Date(row.created_at).toLocaleString(),
  },
  {
    title: "Reason",
    key: "kind",
    render: (row) => (row.kind === "incremental" ? "New datasets" : "Selected rerun"),
  },
  {
    title: "Progress",
    key: "status",
    render: (row) => {
      const completed = row.items.filter((item) => item.status === "completed").length;
      const failed = row.items.filter((item) =>
        ["failed", "cancelled"].includes(item.status),
      ).length;
      return `${completed}/${row.items.length} completed${failed ? ` · ${failed} failed` : ""}`;
    },
  },
  {
    title: "Status",
    key: "status",
    render: (row) =>
      h(
        NTag,
        { type: row.status === "failed" || row.status === "partial" ? "error" : "info" },
        { default: () => row.status },
      ),
  },
  {
    title: "Actions",
    key: "actions",
    width: 120,
    fixed: "right",
    render: (row) => {
      const failed = row.items.some((item) => ["failed", "cancelled"].includes(item.status));
      return failed
        ? h(
            NButton,
            {
              size: "small",
              loading: retryBatchMutation.isPending.value,
              onClick: () => retryBatchMutation.mutate(row.id),
            },
            { default: () => "Retry failed" },
          )
        : "—";
    },
  },
];

const connectorOptions = computed(() =>
  (connectorsQuery.data.value ?? []).map((connector: SourceConnectorResponse) => ({
    label: connector.name,
    value: connector.id,
  })),
);
const profileOptions = computed(() =>
  (profilesQuery.data.value ?? []).map((profile) => ({
    label: `${profile.name} · v${profile.version}`,
    value: profile.id,
  })),
);
const selectedConnector = computed(() =>
  (connectorsQuery.data.value ?? []).find((connector) => connector.id === ruleConnectorId.value),
);
const selectedProvider = computed<SourceProviderDescriptorResponse | undefined>(() =>
  (providersQuery.data.value ?? []).find(
    (provider) => provider.provider_id === selectedConnector.value?.provider_id,
  ),
);
const ruleFieldOptions = computed(() =>
  (selectedProvider.value?.fields ?? []).map((field) => ({
    label: field.label,
    value: field.key,
  })),
);
const selectedRuleField = computed(() =>
  selectedProvider.value?.fields.find((field) => field.key === ruleField.value),
);
const ruleOperatorOptions = computed(() =>
  (selectedRuleField.value?.operators ?? []).map((operator) => ({
    label: operator.replace(/_/g, " "),
    value: operator,
  })),
);
const hasValidRuleValue = computed(() => {
  if (ruleOperator.value === "is_null") return true;
  const value = ruleValue.value.trim();
  if (!value) return false;
  if (ruleOperator.value === "in" || ruleOperator.value === "not_in") {
    return value.split(",").some((item) => item.trim().length > 0);
  }
  if (selectedRuleField.value?.field_type === "number") {
    return Number.isFinite(Number(value));
  }
  if (selectedRuleField.value?.field_type === "boolean") {
    return value.toLowerCase() === "true" || value.toLowerCase() === "false";
  }
  return true;
});
const canCreateRule = computed(
  () =>
    !!ruleName.value.trim() &&
    canManageAutomation.value &&
    !!ruleConnectorId.value &&
    !!ruleProfileId.value &&
    !!ruleField.value &&
    !!ruleOperator.value &&
    hasValidRuleValue.value,
);

function parsedRuleValue(): string | string[] | number | boolean {
  if (ruleOperator.value === "is_null") return true;
  if (ruleOperator.value === "in" || ruleOperator.value === "not_in") {
    return ruleValue.value
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
  }
  if (selectedRuleField.value?.field_type === "number") {
    return Number(ruleValue.value);
  }
  if (selectedRuleField.value?.field_type === "boolean") {
    return ruleValue.value.toLowerCase() === "true";
  }
  return ruleValue.value.trim();
}

function resetRuleForm(): void {
  ruleVisible.value = false;
  ruleName.value = "";
  ruleConnectorId.value = null;
  ruleProfileId.value = null;
  ruleField.value = null;
  ruleOperator.value = null;
  ruleValue.value = "";
}

const createRuleMutation = useMutation({
  mutationFn: () => {
    const payload: CreateMembershipRuleRequest = {
      name: ruleName.value.trim(),
      connector_id: String(ruleConnectorId.value),
      import_profile_version_id: String(ruleProfileId.value),
      condition: {
        combinator: "all",
        children: [
          {
            kind: "predicate",
            field: String(ruleField.value),
            operator: ruleOperator.value as FilterOperator,
            value: parsedRuleValue(),
          },
        ],
      },
    };
    return createMembershipRuleApiV1DatasetCollectionsCollectionIdMembershipRulesPost(
      collectionId.value,
      payload,
    );
  },
  onSuccess: async () => {
    await rulesQuery.refetch();
    message.success("Dynamic membership rule created");
    resetRuleForm();
  },
  onError: (error) => message.error(toUserMessage(error, "Failed to create membership rule")),
});

const runRuleMutation = useMutation({
  mutationFn: (ruleId: string) =>
    runMembershipDiscoveryApiV1DatasetCollectionsCollectionIdMembershipRulesRuleIdRunsPost(
      collectionId.value,
      ruleId,
      { as_of_utc: new Date().toISOString() },
    ),
  onSuccess: async (run) => {
    await Promise.all([rulesQuery.refetch(), refreshCollection()]);
    message.success(
      run.status === "needs_attention"
        ? "Discovery finished and needs attention"
        : "Discovery finished",
    );
  },
  onError: (error) => message.error(toUserMessage(error, "Discovery run failed")),
});

function connectorName(connectorId: string): string {
  return (
    connectorsQuery.data.value?.find((connector) => connector.id === connectorId)?.name ??
    connectorId
  );
}

function ruleConditionCount(condition: unknown): number {
  if (typeof condition !== "object" || condition === null || !("children" in condition)) return 0;
  return Array.isArray(condition.children) ? condition.children.length : 0;
}

const ruleColumns: DataTableColumns<MembershipRuleResponse> = [
  { title: "Rule", key: "name", minWidth: 180 },
  {
    title: "Source",
    key: "connector",
    minWidth: 160,
    render: (rule) => connectorName(rule.active_version.connector_id),
  },
  {
    title: "Conditions",
    key: "conditions",
    minWidth: 150,
    render: (rule) => {
      const count = ruleConditionCount(rule.active_version.condition);
      return `${count} condition${count === 1 ? "" : "s"}`;
    },
  },
  {
    title: "Status",
    key: "status",
    width: 110,
    render: (rule) => h(NTag, { size: "small" }, { default: () => rule.status }),
  },
  {
    title: "Action",
    key: "action",
    width: 110,
    render: (rule) =>
      h(
        NButton,
        {
          size: "small",
          disabled: !canManageAutomation.value,
          loading: runRuleMutation.isPending.value && runRuleMutation.variables.value === rule.id,
          onClick: () => runRuleMutation.mutate(rule.id),
        },
        { default: () => "Run now" },
      ),
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
  {
    title: "Data resolution",
    key: "source_resolution",
    render: (row) =>
      h(
        NTag,
        { type: row.reproducibility_capability ? "success" : "warning" },
        {
          default: () =>
            row.reproducibility_capability ? "Frozen (legacy)" : "Current data at run",
        },
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
      <NTabs
        v-model:value="activeTab"
        type="line"
        animated
        class="collection-tabs"
        :on-before-leave="handleTabBeforeLeave"
      >
        <NTabPane name="overview" tab="Overview">
          <NAlert type="info" :show-icon="false" class="snapshot-explainer">
            <strong>What is a snapshot?</strong>
            It records this Collection's members, rules, and current Dataset change numbers. Data is
            read when a review, training, or prediction run starts; it is not copied or frozen.
          </NAlert>
          <NAlert v-if="!latestReadyRevision" type="info">
            This collection does not have a saved snapshot yet. Save one before using it for review,
            training, or prediction.
          </NAlert>
          <NAlert v-else-if="revisionOutdated" type="warning">
            The collection setup has changed since the latest snapshot. Save a new snapshot to use
            the current setup. Review still opens snapshot r{{
              latestReadyRevision.revision_number
            }}.
          </NAlert>
          <CollectionSnapshotUpdateAlert
            v-if="snapshotUpdateQuery.data.value?.update_available"
            :outdated-member-count="snapshotUpdateQuery.data.value.outdated_member_count"
            :snapshot-revision-number="snapshotUpdateQuery.data.value.snapshot_revision_number"
            :can-modify="canModify"
            :loading="snapshotRefreshMutation.isPending.value"
            @refresh="snapshotRefreshMutation.mutate()"
          />
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
                    <NText depth="3" class="help-label">Latest saved snapshot</NText>
                  </template>
                  The saved Collection setup used to start review, training, and prediction. Member
                  data is resolved when each run starts.
                </NTooltip>
                <strong>{{
                  latestReadyRevision ? `r${latestReadyRevision.revision_number}` : "None"
                }}</strong>
              </div>
            </div>
          </NCard>
        </NTabPane>
        <NTabPane v-if="isScCollection" name="classify" :disabled="!latestReadyRevision">
          <template #tab>
            <NTooltip :disabled="!!latestReadyRevision">
              <template #trigger>
                <span>Classify <span aria-hidden="true">&#8599;</span></span>
              </template>
              Save a snapshot before opening the Classify workspace.
            </NTooltip>
          </template>
        </NTabPane>
        <NTabPane name="data" tab="Data & rules">
          <NCard title="Dynamic membership" class="dynamic-membership-card">
            <template #header-extra>
              <NButton
                type="primary"
                size="small"
                :disabled="!canManageAutomation"
                @click="ruleVisible = true"
              >
                Add rule
              </NButton>
            </template>
            <NAlert type="info" :show-icon="false" class="dynamic-membership-explainer">
              Rules discover new source records and add only newly matched Datasets to this
              Collection. Existing linked Datasets are not re-imported. Run a rule manually now;
              scheduled polling can be configured later.
            </NAlert>
            <NDataTable
              v-if="(rulesQuery.data.value ?? []).length > 0"
              :columns="ruleColumns"
              :data="rulesQuery.data.value ?? []"
              :loading="rulesQuery.isLoading.value"
              :row-key="(row: MembershipRuleResponse) => row.id"
              :scroll-x="700"
              size="small"
            />
            <NEmpty v-else description="No dynamic membership rules yet" />
          </NCard>

          <NCard title="Linked datasets">
            <template #header-extra>
              <NSpace>
                <NButton
                  size="small"
                  :disabled="selectedCoverage.length === 0 || !collection.default_model_id"
                  @click="reconcileVisible = true"
                >
                  Predict selected ({{ selectedCoverage.length }})
                </NButton>
                <NTooltip :disabled="!exportDisabledReason">
                  <template #trigger>
                    <span>
                      <NButton
                        size="small"
                        :disabled="!!exportDisabledReason"
                        @click="exportVisible = true"
                      >
                        Export selected ({{ selectedMembers.length }})
                      </NButton>
                    </span>
                  </template>
                  {{ exportDisabledReason }}
                </NTooltip>
                <NButton
                  type="primary"
                  size="small"
                  :disabled="!canModify"
                  @click="linkVisible = true"
                >
                  Link datasets
                </NButton>
              </NSpace>
            </template>
            <NDataTable
              v-if="members.length > 0"
              v-model:checked-row-keys="selectedCoverageMemberIds"
              :columns="memberColumns"
              :data="members"
              :row-key="(row: DatasetCollectionMemberResponse) => row.id"
              :scroll-x="760"
            />
            <NEmpty v-else description="No datasets linked" />
          </NCard>
        </NTabPane>
        <NTabPane name="models" tab="Models">
          <NCard title="Default prediction model">
            <template #header-extra>
              <NButton size="small" :disabled="!canModify" @click="showModelPicker">
                {{ collection.default_model_id ? "Change model" : "Select model" }}
              </NButton>
            </template>
            <div class="model-binding-summary">
              <div>
                <NText depth="3">Model for newly added datasets</NText>
                <strong>
                  {{
                    collection.default_model_id
                      ? defaultModel?.name || collection.default_model_id
                      : "No default model selected"
                  }}
                </strong>
              </div>
              <NText depth="3">
                Only datasets added after a snapshot is saved are predicted automatically. Changing
                the model never reruns existing datasets.
              </NText>
            </div>
            <NAlert v-if="!collection.default_model_id" type="warning" class="model-status-alert">
              No automatic prediction will start for newly added datasets until a model is chosen.
            </NAlert>
            <NAlert v-else-if="modelMismatchCount > 0" type="error" class="model-status-alert">
              {{ modelMismatchCount }} linked dataset{{
                modelMismatchCount === 1 ? " uses" : "s use"
              }}
              a different model. Select affected rows in Data to rerun them with the default model.
            </NAlert>
            <NText depth="3" class="candidate-training-note">
              Automatic candidate training is not enabled yet. A future version will add readiness
              and regression checks before any model can be promoted.
            </NText>
          </NCard>
        </NTabPane>
        <NTabPane name="snapshots" tab="Snapshots">
          <NCard title="Saved snapshots">
            <NDataTable
              v-if="(revisionsQuery.data.value ?? []).length > 0"
              :columns="revisionColumns"
              :data="revisionsQuery.data.value ?? []"
              :row-key="(row: DatasetCollectionRevisionResponse) => row.id"
              :scroll-x="640"
            />
            <NEmpty v-else description="Save a snapshot to train or predict this collection" />
          </NCard>
        </NTabPane>
        <NTabPane name="activity" tab="Activity">
          <NCard title="Prediction activity">
            <NDataTable
              v-if="(batchesQuery.data.value ?? []).length > 0"
              :columns="batchColumns"
              :data="batchesQuery.data.value ?? []"
              :row-key="(row: CollectionPredictionBatch) => row.id"
              :scroll-x="760"
            />
            <NEmpty v-else description="Prediction batches will appear here" />
          </NCard>
        </NTabPane>
      </NTabs>
    </template>

    <NModal
      v-model:show="exportVisible"
      preset="card"
      title="Export selected Collection records"
      :style="{ width: 'min(920px, calc(100vw - 32px))' }"
    >
      <NAlert type="info" :show-icon="false" class="collection-export-note">
        {{ selectedMembers.length }} linked Dataset record{{
          selectedMembers.length === 1 ? "" : "s"
        }}
        selected. Parquet stays combined; KLARF creates one complete numbered file per inspection.
      </NAlert>
      <PredictionExportPlugin
        :collection-id="collectionId"
        :member-ids="selectedCoverageMemberIds"
        :member-dataset-ids="selectedMemberDatasetIds"
        :on-complete="closeExport"
        :on-cancel="closeExport"
      />
    </NModal>

    <NModal
      v-model:show="ruleVisible"
      preset="card"
      title="Add dynamic membership rule"
      :style="{ width: 'min(680px, calc(100vw - 32px))' }"
    >
      <NAlert v-if="connectorOptions.length === 0" type="warning" :show-icon="false">
        An administrator must configure a source connector and import profile before rules can be
        created.
      </NAlert>
      <template v-else>
        <NText depth="3" class="rule-intro">
          When this rule runs, each newly matched source record is imported as a standalone Dataset
          and linked to this Collection. Existing matches are skipped.
        </NText>
        <NFormItem label="Rule name" required>
          <NInput v-model:value="ruleName" placeholder="For example: Line A metal layers" />
        </NFormItem>
        <NFormItem label="Source" required>
          <NSelect
            v-model:value="ruleConnectorId"
            :options="connectorOptions"
            placeholder="Choose a configured source"
            @update:value="
              () => {
                ruleProfileId = null;
                ruleField = null;
                ruleOperator = null;
              }
            "
          />
        </NFormItem>
        <NFormItem label="Import profile" required>
          <NSelect
            v-model:value="ruleProfileId"
            :options="profileOptions"
            :loading="profilesQuery.isLoading.value"
            :disabled="!ruleConnectorId || profileOptions.length === 0"
            placeholder="Choose how matched records become Datasets"
          />
        </NFormItem>
        <NAlert
          v-if="ruleConnectorId && !profilesQuery.isLoading.value && profileOptions.length === 0"
          type="warning"
          :show-icon="false"
        >
          This source has no import profile. Ask an administrator to add one.
        </NAlert>
        <div class="rule-condition-row">
          <NFormItem label="Field" required>
            <NSelect
              v-model:value="ruleField"
              :options="ruleFieldOptions"
              :disabled="!ruleConnectorId"
              placeholder="Choose a field"
              @update:value="ruleOperator = null"
            />
          </NFormItem>
          <NFormItem label="Condition" required>
            <NSelect
              v-model:value="ruleOperator"
              :options="ruleOperatorOptions"
              :disabled="!ruleField"
              placeholder="Choose a condition"
            />
          </NFormItem>
          <NFormItem
            v-if="ruleOperator !== 'is_null'"
            label="Value"
            required
            :validation-status="ruleValue.trim() && !hasValidRuleValue ? 'error' : undefined"
            :feedback="
              ruleValue.trim() && !hasValidRuleValue
                ? selectedRuleField?.field_type === 'number'
                  ? 'Enter a valid number.'
                  : selectedRuleField?.field_type === 'boolean'
                    ? 'Enter true or false.'
                    : 'Enter at least one value.'
                : undefined
            "
          >
            <NInput
              v-model:value="ruleValue"
              :placeholder="
                ruleOperator === 'in' || ruleOperator === 'not_in'
                  ? 'Separate values with commas'
                  : 'Enter a value'
              "
            />
          </NFormItem>
        </div>
      </template>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="resetRuleForm">Cancel</NButton>
          <NButton
            type="primary"
            :disabled="!canCreateRule"
            :loading="createRuleMutation.isPending.value"
            @click="createRuleMutation.mutate()"
          >
            Create rule
          </NButton>
        </NSpace>
      </template>
    </NModal>

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

    <NModal
      v-model:show="modelVisible"
      preset="card"
      title="Default prediction model"
      :style="{ width: 'min(960px, calc(100vw - 32px))' }"
    >
      <NText depth="3">
        The selected model applies only to newly added datasets. Existing results stay unchanged
        until you select and rerun them.
      </NText>
      <RemoteModelPicker
        v-model="selectedDefaultModelId"
        class="model-select"
        :active="modelVisible"
        :compatible-view-ids="collection ? [collection.target_view_id] : []"
      />
      <template #footer>
        <NSpace justify="space-between">
          <NPopconfirm
            :disabled="!collection?.default_model_id"
            @positive-click="defaultModelMutation.mutate(null)"
          >
            <template #trigger>
              <NButton
                type="error"
                ghost
                :disabled="!collection?.default_model_id"
                :loading="defaultModelMutation.isPending.value"
              >
                Clear default
              </NButton>
            </template>
            New datasets will no longer start prediction automatically.
          </NPopconfirm>
          <NSpace>
            <NButton @click="modelVisible = false">Cancel</NButton>
            <NButton
              type="primary"
              :disabled="!selectedDefaultModelId"
              :loading="defaultModelMutation.isPending.value"
              @click="defaultModelMutation.mutate(selectedDefaultModelId)"
            >
              Save model
            </NButton>
          </NSpace>
        </NSpace>
      </template>
    </NModal>

    <NModal
      v-model:show="reconcileVisible"
      preset="card"
      title="Predict selected datasets"
      :style="{ width: 'min(560px, calc(100vw - 32px))' }"
    >
      <NAlert type="warning" :show-icon="false">
        This starts {{ selectedCoverage.length }} prediction job{{
          selectedCoverage.length === 1 ? "" : "s"
        }}
        using {{ defaultModel?.name || collection?.default_model_id }} and snapshot
        {{ latestReadyRevision ? `r${latestReadyRevision.revision_number}` : "—" }}. Each dataset
        runs separately, so failed items can be retried without rerunning successful ones.
      </NAlert>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="reconcileVisible = false">Cancel</NButton>
          <NButton
            type="primary"
            :disabled="selectedCoverage.length === 0"
            :loading="reconcileMutation.isPending.value"
            @click="reconcileMutation.mutate()"
          >
            Start prediction
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

.collection-tabs :deep(.n-tab-pane) {
  display: grid;
  gap: 16px;
  padding-top: 14px;
}

.dynamic-membership-explainer {
  margin-bottom: 14px;
}

.rule-intro {
  display: block;
  margin-bottom: 16px;
}

.rule-condition-row {
  display: grid;
  grid-template-columns: minmax(150px, 1fr) minmax(150px, 0.8fr) minmax(180px, 1fr);
  gap: 10px;
}

.model-binding-summary {
  display: grid;
  grid-template-columns: minmax(180px, 0.35fr) minmax(260px, 1fr);
  gap: 24px;
  align-items: start;
}

.model-binding-summary > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.model-binding-summary strong {
  overflow-wrap: anywhere;
}

.model-status-alert,
.candidate-training-note {
  margin-top: 14px;
}

.candidate-training-note {
  display: block;
}

.model-select {
  margin-top: 18px;
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

  .model-binding-summary {
    grid-template-columns: 1fr;
    gap: 10px;
  }

  .rule-condition-row {
    grid-template-columns: 1fr;
    gap: 0;
  }
}
</style>
