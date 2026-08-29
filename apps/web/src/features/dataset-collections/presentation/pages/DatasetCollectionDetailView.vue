<script setup lang="ts">
import { computed, h, ref } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
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
  createScAutomationPartitionApiV1DatasetCollectionsCollectionIdScAutomationPartitionsPost,
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
  listScAutomationPartitionsApiV1DatasetCollectionsCollectionIdScAutomationPartitionsGet,
  unlinkMemberApiV1DatasetCollectionsCollectionIdMembersMemberIdDelete,
  runMembershipDiscoveryApiV1DatasetCollectionsCollectionIdMembershipRulesRuleIdRunsPost,
} from "@/generated/orval/endpoints/api";
import type {
  Dataset,
  DatasetCollectionResponse,
  DatasetCollectionMemberResponse,
  DatasetCollectionRevisionResponse,
  CreateMembershipRuleRequest,
  CreateScAutomationPartitionRequestDimension,
  FilterOperator,
  MembershipRuleResponse,
  ScAutomationPartitionResponse,
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
import { getScClassifyLimits } from "@/features/sc/api/classifyLimits";
import { supportsScPredictionExport } from "@/features/sc/domain/predictionExportCapability";
import { useAuthStore } from "@/features/auth/application/store";
import { useOrgStore } from "@/features/auth/application/org";
import { orgScopedQueryKey, toUserMessage } from "@/shared/api";
import RemoteModelPicker from "@/features/models/presentation/components/RemoteModelPicker.vue";
import { formatDateTime, formatNumber } from "@/shared/i18n/format";

const route = useRoute();
const { t } = useI18n();
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
const partitionVisible = ref(false);
const partitionName = ref("");
const partitionConnectorId = ref<string | null>(null);
const partitionProfileId = ref<string | null>(null);
const partitionLayerId = ref("");
const partitionDimension = ref<CreateScAutomationPartitionRequestDimension>("device");
const partitionDimensionValue = ref("");

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
const partitionProfilesQuery = useQuery({
  queryKey: computed(() =>
    orgScopedQueryKey(orgStore.currentOrgId, [
      "source-connectors",
      partitionConnectorId.value ?? "none",
      "import-profiles",
    ]),
  ),
  queryFn: () =>
    listImportProfilesApiV1SourceConnectorsConnectorIdImportProfilesGet(
      String(partitionConnectorId.value),
    ),
  enabled: computed(() => !!orgStore.currentOrgId && !!partitionConnectorId.value),
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
const partitionsQuery = useQuery({
  queryKey: computed(() =>
    orgScopedQueryKey(orgStore.currentOrgId, [
      "dataset-collections",
      collectionId.value,
      "sc-automation-partitions",
    ]),
  ),
  queryFn: () =>
    listScAutomationPartitionsApiV1DatasetCollectionsCollectionIdScAutomationPartitionsGet(
      collectionId.value,
    ),
  enabled: computed(() => !!orgStore.currentOrgId && !!collectionId.value && isScCollection.value),
});
const classifyLimitsQuery = useQuery({
  queryKey: ["sc", "classify-limits"],
  queryFn: getScClassifyLimits,
  enabled: isScCollection,
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
const classifyExceedsLimit = computed(() => {
  const rows = latestReadyRevision.value?.row_count;
  const maximum = classifyLimitsQuery.data.value?.max_rows;
  return rows !== null && rows !== undefined && maximum !== undefined && rows > maximum;
});
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
    if (version === undefined) throw new Error(t("collectionDetail.definitionMissing"));
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
    message.success(t("collectionDetail.linked"));
    linkVisible.value = false;
    selectedDatasetIds.value = [];
    await refreshCollection();
  },
  onError: (error) => message.error(toUserMessage(error, t("collectionDetail.linkFailed"))),
});

const unlinkMutation = useMutation({
  mutationFn: (member: DatasetCollectionMemberResponse) => {
    const version = collection.value?.definition_version;
    if (version === undefined) throw new Error(t("collectionDetail.definitionMissing"));
    return unlinkMemberApiV1DatasetCollectionsCollectionIdMembersMemberIdDelete(
      collectionId.value,
      member.id,
      { expected_definition_version: version },
    );
  },
  onSuccess: async () => {
    message.success(t("collectionDetail.unlinked"));
    await refreshCollection();
  },
  onError: (error) => message.error(toUserMessage(error, t("collectionDetail.unlinkFailed"))),
});

const revisionMutation = useMutation({
  mutationFn: () => {
    const version = collection.value?.definition_version;
    if (version === undefined) throw new Error(t("collectionDetail.definitionMissing"));
    return createRevisionApiV1DatasetCollectionsCollectionIdRevisionsPost(collectionId.value, {
      expected_definition_version: version,
    });
  },
  onSuccess: async () => {
    message.success(t("collectionDetail.snapshotSaved"));
    await refreshCollection();
  },
  onError: (error) =>
    message.error(toUserMessage(error, t("collectionDetail.snapshotCreateFailed"))),
});

const snapshotRefreshMutation = useMutation({
  mutationFn: () => {
    const version = collection.value?.definition_version;
    if (version === undefined) throw new Error(t("collectionDetail.definitionMissing"));
    return refreshCollectionSnapshot(collectionId.value, {
      expected_definition_version: version,
    });
  },
  onSuccess: async (result) => {
    message.success(
      result.outcome === "refreshed"
        ? t("collectionDetail.snapshotRefreshed", { revision: result.snapshot.revision_number })
        : t("collectionDetail.snapshotCurrent"),
    );
    await refreshCollection();
  },
  onError: (error) =>
    message.error(toUserMessage(error, t("collectionDetail.snapshotRefreshFailed"))),
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
  if (selectedMembers.value.length === 0) return t("collectionDetail.selectExport");
  if (
    selectedExportDatasets.value.length !== selectedMembers.value.length ||
    selectedExportDatasets.value.some((dataset) => !supportsScPredictionExport(dataset))
  ) {
    return t("collectionDetail.exportRequiresSc");
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
    if (bindingVersion === undefined) throw new Error(t("collectionDetail.modelSettingMissing"));
    return updateCollectionDefaultModel(collectionId.value, {
      expected_binding_version: bindingVersion,
      model_id: modelId,
    });
  },
  onSuccess: async () => {
    modelVisible.value = false;
    message.success(
      selectedDefaultModelId.value
        ? t("collectionDetail.modelUpdated")
        : t("collectionDetail.modelCleared"),
    );
    await refreshCollection();
  },
  onError: (error) => message.error(toUserMessage(error, t("collectionDetail.modelUpdateFailed"))),
});

const reconcileMutation = useMutation({
  mutationFn: () => {
    const snapshot = latestReadyRevision.value;
    const modelId = collection.value?.default_model_id;
    if (!snapshot || !modelId) throw new Error(t("collectionDetail.predictionRequirements"));
    return createCollectionPredictionBatch(collectionId.value, {
      snapshot_id: snapshot.id,
      expected_default_model_id: modelId,
      request_id: crypto.randomUUID(),
      dataset_ids: selectedCoverage.value.map((item) => item.dataset_id),
    });
  },
  onSuccess: async () => {
    message.success(t("collectionDetail.predictionStarted"));
    reconcileVisible.value = false;
    selectedCoverageMemberIds.value = [];
    await refreshCollection();
  },
  onError: (error) => message.error(toUserMessage(error, t("collectionDetail.predictionFailed"))),
});

const retryBatchMutation = useMutation({
  mutationFn: (batchId: string) => retryCollectionPredictionBatch(collectionId.value, batchId),
  onSuccess: async () => {
    message.success(t("collectionDetail.retryStarted"));
    await refreshCollection();
  },
  onError: (error) => message.error(toUserMessage(error, t("collectionDetail.retryFailed"))),
});

function coverageLabel(item: CollectionPredictionCoverage | undefined): string {
  if (!item) {
    if (!latestReadyRevision.value) return t("collectionDetail.noSnapshotReview");
    if (coverageQuery.isLoading.value) return t("collectionDetail.loading");
    if (coverageQuery.isError.value) return t("collectionDetail.unavailable");
    return t("collectionDetail.notEvaluated");
  }
  if (item.active_prediction_status === "running") return t("collectionDetail.predictionRunning");
  if (item.active_prediction_status === "queued") return t("collectionDetail.predictionQueued");
  if (item.status === "current") return t("collectionDetail.current");
  if (item.status === "model_mismatch") return t("collectionDetail.differentModel");
  if (item.status === "data_outdated") return t("collectionDetail.datasetChanged");
  return t("collectionDetail.notPredicted");
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
  if (classifyExceedsLimit.value) {
    message.warning(
      t("collectionDetail.classifyTooLarge", {
        rows: formatNumber(revision.row_count ?? 0),
        maximum: formatNumber(classifyLimitsQuery.data.value?.max_rows ?? 0),
      }),
    );
    return;
  }
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
  { title: t("collectionDetail.order"), key: "position", width: 80 },
  {
    title: t("collectionDetail.dataset"),
    key: "source_dataset_id",
    minWidth: 180,
    render: (row) => datasetById.value.get(row.source_dataset_id)?.name ?? row.source_dataset_id,
  },
  {
    title: t("collectionDetail.prediction"),
    key: "prediction",
    minWidth: 150,
    render: (row) => {
      const item = coverageByMemberId.value.get(row.id);
      return h(NTag, { type: coverageTagType(item) }, { default: () => coverageLabel(item) });
    },
  },
  {
    title: t("collectionDetail.actions"),
    key: "actions",
    width: 250,
    fixed: "right",
    render: (row) =>
      h(NSpace, null, {
        default: () => [
          h(
            NButton,
            { size: "small", onClick: () => router.push(`/datasets/${row.source_dataset_id}`) },
            { default: () => t("collectionDetail.openStandalone") },
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
            { default: () => t("collectionDetail.unlink") },
          ),
        ],
      }),
  },
];

const batchColumns: DataTableColumns<CollectionPredictionBatch> = [
  {
    title: t("collectionDetail.started"),
    key: "created_at",
    width: 180,
    render: (row) => formatDateTime(row.created_at),
  },
  {
    title: t("collectionDetail.reason"),
    key: "kind",
    render: (row) =>
      row.kind === "incremental"
        ? t("collectionDetail.newDatasets")
        : t("collectionDetail.selectedRerun"),
  },
  {
    title: t("collectionDetail.progress"),
    key: "status",
    render: (row) => {
      const completed = row.items.filter((item) => item.status === "completed").length;
      const failed = row.items.filter((item) =>
        ["failed", "cancelled"].includes(item.status),
      ).length;
      const progress = t("collectionDetail.completedProgress", {
        completed: formatNumber(completed),
        total: formatNumber(row.items.length),
      });
      return failed
        ? `${progress} · ${t("collectionDetail.failedProgress", { count: formatNumber(failed) })}`
        : progress;
    },
  },
  {
    title: t("collectionDetail.status"),
    key: "status",
    render: (row) =>
      h(
        NTag,
        { type: row.status === "failed" || row.status === "partial" ? "error" : "info" },
        { default: () => t(`status.${row.status}`, row.status) },
      ),
  },
  {
    title: t("collectionDetail.actions"),
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
            { default: () => t("collectionDetail.retryFailedItems") },
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
const scConnectorOptions = computed(() =>
  (connectorsQuery.data.value ?? [])
    .filter((connector) => connector.provider_id === "sc" && connector.enabled)
    .map((connector) => ({ label: connector.name, value: connector.id })),
);
const partitionProfileOptions = computed(() =>
  (partitionProfilesQuery.data.value ?? []).map((profile) => ({
    label: `${profile.name} · v${profile.version}`,
    value: profile.id,
  })),
);
const partitionDimensionOptions = computed(() => [
  { label: t("collectionDetail.partitionDevice"), value: "device" },
  { label: t("collectionDetail.partitionRecipe"), value: "recipe_id" },
]);
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
    message.success(t("collectionDetail.ruleCreated"));
    resetRuleForm();
  },
  onError: (error) => message.error(toUserMessage(error, t("collectionDetail.ruleCreateFailed"))),
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
        ? t("collectionDetail.discoveryAttention")
        : t("collectionDetail.discoveryFinished"),
    );
  },
  onError: (error) => message.error(toUserMessage(error, t("collectionDetail.discoveryFailed"))),
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
  { title: t("collectionDetail.rule"), key: "name", minWidth: 180 },
  {
    title: t("collectionDetail.source"),
    key: "connector",
    minWidth: 160,
    render: (rule) => connectorName(rule.active_version.connector_id),
  },
  {
    title: t("collectionDetail.conditions"),
    key: "conditions",
    minWidth: 150,
    render: (rule) => {
      const count = ruleConditionCount(rule.active_version.condition);
      return t("collectionDetail.conditionCount", { count }, count);
    },
  },
  {
    title: t("collectionDetail.status"),
    key: "status",
    width: 110,
    render: (rule) => h(NTag, { size: "small" }, { default: () => rule.status }),
  },
  {
    title: t("collectionDetail.action"),
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
        { default: () => t("collectionDetail.runNow") },
      ),
  },
];

const canCreatePartition = computed(
  () =>
    canManageAutomation.value &&
    !!partitionName.value.trim() &&
    !!partitionConnectorId.value &&
    !!partitionProfileId.value &&
    !!partitionLayerId.value.trim() &&
    !!partitionDimensionValue.value.trim(),
);

function resetPartitionForm(): void {
  partitionVisible.value = false;
  partitionName.value = "";
  partitionConnectorId.value = null;
  partitionProfileId.value = null;
  partitionLayerId.value = "";
  partitionDimension.value = "device";
  partitionDimensionValue.value = "";
}

const createPartitionMutation = useMutation({
  mutationFn: () =>
    createScAutomationPartitionApiV1DatasetCollectionsCollectionIdScAutomationPartitionsPost(
      collectionId.value,
      {
        name: partitionName.value.trim(),
        connector_id: String(partitionConnectorId.value),
        import_profile_version_id: String(partitionProfileId.value),
        layer_id: partitionLayerId.value.trim(),
        dimension: partitionDimension.value,
        dimension_value: partitionDimensionValue.value.trim(),
      },
    ),
  onSuccess: async () => {
    await Promise.all([partitionsQuery.refetch(), rulesQuery.refetch()]);
    message.success(t("collectionDetail.partitionCreated"));
    resetPartitionForm();
  },
  onError: (error) =>
    message.error(toUserMessage(error, t("collectionDetail.partitionCreateFailed"))),
});

const partitionColumns: DataTableColumns<ScAutomationPartitionResponse> = [
  {
    title: t("collectionDetail.source"),
    key: "connector_id",
    minWidth: 160,
    render: (partition) => connectorName(partition.connector_id),
  },
  { title: t("collectionDetail.partitionLayer"), key: "layer_id", minWidth: 130 },
  {
    title: t("collectionDetail.partitionDimension"),
    key: "dimension",
    minWidth: 130,
    render: (partition) =>
      partition.dimension === "device"
        ? t("collectionDetail.partitionDevice")
        : t("collectionDetail.partitionRecipe"),
  },
  {
    title: t("collectionDetail.partitionValue"),
    key: "dimension_value",
    minWidth: 160,
  },
  {
    title: t("collectionDetail.created"),
    key: "created_at",
    width: 180,
    render: (partition) => formatDateTime(partition.created_at),
  },
];

const revisionColumns: DataTableColumns<DatasetCollectionRevisionResponse> = [
  {
    title: t("collectionDetail.snapshot"),
    key: "revision_number",
    render: (row) => `r${row.revision_number}`,
  },
  {
    title: t("collectionDetail.savedFromSetup"),
    key: "definition_version",
    render: (row) => `v${row.definition_version}`,
  },
  {
    title: t("collectionDetail.status"),
    key: "status",
    render: (row) =>
      h(
        NTag,
        { type: row.status === "ready" ? "success" : "error" },
        {
          default: () =>
            row.status === "ready"
              ? t("collectionDetail.readyToUse")
              : t("collectionDetail.failed"),
        },
      ),
  },
  {
    title: t("collectionDetail.dataResolution"),
    key: "source_resolution",
    render: (row) =>
      h(
        NTag,
        { type: row.reproducibility_capability ? "success" : "warning" },
        {
          default: () =>
            row.reproducibility_capability
              ? t("collectionDetail.frozenLegacy")
              : t("collectionDetail.currentDataAtRun"),
        },
      ),
  },
  {
    title: t("collectionDetail.rows"),
    key: "row_count",
    render: (row) => (row.row_count === null ? "—" : formatNumber(row.row_count)),
  },
  {
    title: t("collectionDetail.created"),
    key: "created_at",
    width: 180,
    render: (row) => formatDateTime(row.created_at),
  },
];
</script>

<template>
  <div class="collection-detail-page">
    <div class="collection-detail-header">
      <div>
        <NButton text size="small" @click="router.push('/dataset-collections')">
          {{ t("collectionDetail.back") }}
        </NButton>
        <h1>{{ collection?.name ?? t("collectionDetail.fallbackName") }}</h1>
        <NText depth="3">{{ collection?.description }}</NText>
      </div>
      <NSpace class="collection-header-actions" :wrap="true">
        <NButton
          :disabled="members.length === 0 || !canModify"
          :loading="revisionMutation.isPending.value"
          :type="revisionOutdated ? 'primary' : 'default'"
          @click="revisionMutation.mutate()"
        >
          {{
            latestReadyRevision
              ? t("collectionDetail.saveSnapshot")
              : t("collectionDetail.saveFirstSnapshot")
          }}
        </NButton>
        <NButton
          :type="revisionOutdated ? 'default' : 'primary'"
          :disabled="!latestReadyRevision || classifyExceedsLimit"
          @click="openStack"
        >
          {{
            latestReadyRevision
              ? t("collectionDetail.reviewSnapshot", {
                  revision: latestReadyRevision.revision_number,
                })
              : t("collectionDetail.noSnapshotReview")
          }}
        </NButton>
      </NSpace>
    </div>

    <div v-if="isLoading" class="collection-loading"><NSpin size="large" /></div>
    <NAlert v-else-if="loadError" type="error">
      {{ toUserMessage(loadError, t("collectionDetail.loadFailed")) }}
    </NAlert>
    <template v-else-if="collection">
      <NAlert v-if="!canModify" type="info">
        {{ t("collectionDetail.readOnly") }}
      </NAlert>
      <NTabs
        v-model:value="activeTab"
        type="line"
        animated
        class="collection-tabs"
        :on-before-leave="handleTabBeforeLeave"
      >
        <NTabPane name="overview" :tab="t('collectionDetail.overview')">
          <NAlert type="info" :show-icon="false" class="snapshot-explainer">
            <strong>{{ t("collectionDetail.snapshotQuestion") }}</strong>
            {{ t("collectionDetail.snapshotExplanation") }}
          </NAlert>
          <NAlert v-if="!latestReadyRevision" type="info">
            {{ t("collectionDetail.noSnapshot") }}
          </NAlert>
          <NAlert v-else-if="revisionOutdated" type="warning">
            {{
              t("collectionDetail.outdatedSnapshot", {
                revision: latestReadyRevision.revision_number,
              })
            }}
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
                <NText depth="3">{{ t("collections.targetView") }}</NText>
                <strong>{{ collection.target_view_id }}</strong>
              </div>
              <div class="collection-summary-field">
                <NTooltip>
                  <template #trigger>
                    <NText depth="3" class="help-label">{{
                      t("collectionDetail.currentSetupVersion")
                    }}</NText>
                  </template>
                  {{ t("collectionDetail.currentSetupHelp") }}
                </NTooltip>
                <strong>v{{ collection.definition_version }}</strong>
              </div>
              <div class="collection-summary-field">
                <NText depth="3">{{ t("collectionDetail.linkedDatasets") }}</NText>
                <strong>{{ formatNumber(members.length) }}</strong>
              </div>
              <div class="collection-summary-field">
                <NTooltip>
                  <template #trigger>
                    <NText depth="3" class="help-label">{{
                      t("collectionDetail.latestSnapshot")
                    }}</NText>
                  </template>
                  {{ t("collectionDetail.latestSnapshotHelp") }}
                </NTooltip>
                <strong>{{
                  latestReadyRevision
                    ? `r${latestReadyRevision.revision_number}`
                    : t("collectionDetail.none")
                }}</strong>
              </div>
            </div>
          </NCard>
        </NTabPane>
        <NTabPane
          v-if="isScCollection"
          name="classify"
          :disabled="!latestReadyRevision || classifyExceedsLimit"
        >
          <template #tab>
            <NTooltip :disabled="!!latestReadyRevision && !classifyExceedsLimit">
              <template #trigger>
                <span>{{ t("collectionDetail.classify") }}</span>
              </template>
              {{
                classifyExceedsLimit
                  ? t("collectionDetail.classifyTooLarge", {
                      rows: formatNumber(latestReadyRevision?.row_count ?? 0),
                      maximum: formatNumber(classifyLimitsQuery.data.value?.max_rows ?? 0),
                    })
                  : t("collectionDetail.classifyNeedsSnapshot")
              }}
            </NTooltip>
          </template>
        </NTabPane>
        <NTabPane name="data" :tab="t('collectionDetail.dataRules')">
          <NCard
            v-if="isScCollection"
            :title="t('collectionDetail.automationPartitions')"
            class="dynamic-membership-card"
          >
            <template #header-extra>
              <NButton
                type="primary"
                size="small"
                :disabled="!canManageAutomation"
                @click="partitionVisible = true"
              >
                {{ t("collectionDetail.assignPartition") }}
              </NButton>
            </template>
            <NAlert type="info" :show-icon="false" class="dynamic-membership-explainer">
              {{ t("collectionDetail.automationPartitionsHelp") }}
            </NAlert>
            <NDataTable
              v-if="(partitionsQuery.data.value ?? []).length > 0"
              :columns="partitionColumns"
              :data="partitionsQuery.data.value ?? []"
              :loading="partitionsQuery.isLoading.value"
              :row-key="(row: ScAutomationPartitionResponse) => row.id"
              :scroll-x="760"
              size="small"
            />
            <NEmpty v-else :description="t('collectionDetail.noAutomationPartitions')" />
          </NCard>

          <NCard :title="t('collectionDetail.dynamicMembership')" class="dynamic-membership-card">
            <template #header-extra>
              <NButton
                type="primary"
                size="small"
                :disabled="!canManageAutomation"
                @click="ruleVisible = true"
              >
                {{ t("collectionDetail.addRule") }}
              </NButton>
            </template>
            <NAlert type="info" :show-icon="false" class="dynamic-membership-explainer">
              {{ t("collectionDetail.dynamicMembershipHelp") }}
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
            <NEmpty v-else :description="t('collectionDetail.noRules')" />
          </NCard>

          <NCard :title="t('collectionDetail.linkedDatasets')">
            <template #header-extra>
              <NSpace>
                <NButton
                  size="small"
                  :disabled="selectedCoverage.length === 0 || !collection.default_model_id"
                  @click="reconcileVisible = true"
                >
                  {{ t("collectionDetail.predictSelected", { count: selectedCoverage.length }) }}
                </NButton>
                <NTooltip :disabled="!exportDisabledReason">
                  <template #trigger>
                    <span>
                      <NButton
                        size="small"
                        :disabled="!!exportDisabledReason"
                        @click="exportVisible = true"
                      >
                        {{
                          t("collectionDetail.exportSelected", { count: selectedMembers.length })
                        }}
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
                  {{ t("collectionDetail.linkDatasets") }}
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
            <NEmpty v-else :description="t('collectionDetail.noLinkedDatasets')" />
          </NCard>
        </NTabPane>
        <NTabPane name="models" :tab="t('collectionDetail.models')">
          <NCard :title="t('collectionDetail.defaultModel')">
            <template #header-extra>
              <NButton size="small" :disabled="!canModify" @click="showModelPicker">
                {{
                  collection.default_model_id
                    ? t("collectionDetail.changeModel")
                    : t("collectionDetail.selectModel")
                }}
              </NButton>
            </template>
            <div class="model-binding-summary">
              <div>
                <NText depth="3">{{ t("collectionDetail.newDatasetModel") }}</NText>
                <strong>
                  {{
                    collection.default_model_id
                      ? defaultModel?.name || collection.default_model_id
                      : t("collectionDetail.noDefaultModel")
                  }}
                </strong>
              </div>
              <NText depth="3">
                {{ t("collectionDetail.modelBehavior") }}
              </NText>
            </div>
            <NAlert v-if="!collection.default_model_id" type="warning" class="model-status-alert">
              {{ t("collectionDetail.noAutomaticPrediction") }}
            </NAlert>
            <NAlert v-else-if="modelMismatchCount > 0" type="error" class="model-status-alert">
              {{
                t(
                  "collectionDetail.modelMismatch",
                  { count: modelMismatchCount },
                  modelMismatchCount,
                )
              }}
            </NAlert>
            <NText depth="3" class="candidate-training-note">
              {{ t("collectionDetail.candidateTraining") }}
            </NText>
          </NCard>
        </NTabPane>
        <NTabPane name="snapshots" :tab="t('collectionDetail.snapshots')">
          <NCard :title="t('collectionDetail.savedSnapshots')">
            <NDataTable
              v-if="(revisionsQuery.data.value ?? []).length > 0"
              :columns="revisionColumns"
              :data="revisionsQuery.data.value ?? []"
              :row-key="(row: DatasetCollectionRevisionResponse) => row.id"
              :scroll-x="640"
            />
            <NEmpty v-else :description="t('collectionDetail.snapshotEmpty')" />
          </NCard>
        </NTabPane>
        <NTabPane name="activity" :tab="t('collectionDetail.activity')">
          <NCard :title="t('collectionDetail.predictionActivity')">
            <NDataTable
              v-if="(batchesQuery.data.value ?? []).length > 0"
              :columns="batchColumns"
              :data="batchesQuery.data.value ?? []"
              :row-key="(row: CollectionPredictionBatch) => row.id"
              :scroll-x="760"
            />
            <NEmpty v-else :description="t('collectionDetail.batchesEmpty')" />
          </NCard>
        </NTabPane>
      </NTabs>
    </template>

    <NModal
      v-model:show="exportVisible"
      preset="card"
      :title="t('collectionDetail.exportTitle')"
      :style="{ width: 'min(920px, calc(100vw - 32px))' }"
    >
      <NAlert type="info" :show-icon="false" class="collection-export-note">
        {{
          t(
            "collectionDetail.exportSummary",
            { count: selectedMembers.length },
            selectedMembers.length,
          )
        }}
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
      :title="t('collectionDetail.addRuleTitle')"
      :style="{ width: 'min(680px, calc(100vw - 32px))' }"
    >
      <NAlert v-if="connectorOptions.length === 0" type="warning" :show-icon="false">
        {{ t("collectionDetail.connectorRequired") }}
      </NAlert>
      <template v-else>
        <NText depth="3" class="rule-intro">
          {{ t("collectionDetail.ruleIntro") }}
        </NText>
        <NFormItem :label="t('collectionDetail.ruleName')" required>
          <NInput v-model:value="ruleName" :placeholder="t('collectionDetail.ruleExample')" />
        </NFormItem>
        <NFormItem :label="t('collectionDetail.source')" required>
          <NSelect
            v-model:value="ruleConnectorId"
            :options="connectorOptions"
            :placeholder="t('collectionDetail.chooseSource')"
            @update:value="
              () => {
                ruleProfileId = null;
                ruleField = null;
                ruleOperator = null;
              }
            "
          />
        </NFormItem>
        <NFormItem :label="t('collectionDetail.importProfile')" required>
          <NSelect
            v-model:value="ruleProfileId"
            :options="profileOptions"
            :loading="profilesQuery.isLoading.value"
            :disabled="!ruleConnectorId || profileOptions.length === 0"
            :placeholder="t('collectionDetail.chooseProfile')"
          />
        </NFormItem>
        <NAlert
          v-if="ruleConnectorId && !profilesQuery.isLoading.value && profileOptions.length === 0"
          type="warning"
          :show-icon="false"
        >
          {{ t("collectionDetail.noProfile") }}
        </NAlert>
        <div class="rule-condition-row">
          <NFormItem :label="t('collectionDetail.field')" required>
            <NSelect
              v-model:value="ruleField"
              :options="ruleFieldOptions"
              :disabled="!ruleConnectorId"
              :placeholder="t('collectionDetail.chooseField')"
              @update:value="ruleOperator = null"
            />
          </NFormItem>
          <NFormItem :label="t('collectionDetail.condition')" required>
            <NSelect
              v-model:value="ruleOperator"
              :options="ruleOperatorOptions"
              :disabled="!ruleField"
              :placeholder="t('collectionDetail.chooseCondition')"
            />
          </NFormItem>
          <NFormItem
            v-if="ruleOperator !== 'is_null'"
            :label="t('collectionDetail.value')"
            required
            :validation-status="ruleValue.trim() && !hasValidRuleValue ? 'error' : undefined"
            :feedback="
              ruleValue.trim() && !hasValidRuleValue
                ? selectedRuleField?.field_type === 'number'
                  ? t('collectionDetail.validNumber')
                  : selectedRuleField?.field_type === 'boolean'
                    ? t('collectionDetail.validBoolean')
                    : t('collectionDetail.atLeastOneValue')
                : undefined
            "
          >
            <NInput
              v-model:value="ruleValue"
              :placeholder="
                ruleOperator === 'in' || ruleOperator === 'not_in'
                  ? t('collectionDetail.commaValues')
                  : t('collectionDetail.enterValue')
              "
            />
          </NFormItem>
        </div>
      </template>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="resetRuleForm">{{ t("common.cancel") }}</NButton>
          <NButton
            type="primary"
            :disabled="!canCreateRule"
            :loading="createRuleMutation.isPending.value"
            @click="createRuleMutation.mutate()"
          >
            {{ t("collectionDetail.createRule") }}
          </NButton>
        </NSpace>
      </template>
    </NModal>

    <NModal
      v-model:show="partitionVisible"
      preset="card"
      :title="t('collectionDetail.assignPartitionTitle')"
      :style="{ width: 'min(680px, calc(100vw - 32px))' }"
    >
      <NAlert v-if="scConnectorOptions.length === 0" type="warning" :show-icon="false">
        {{ t("collectionDetail.scConnectorRequired") }}
      </NAlert>
      <template v-else>
        <NAlert type="info" :show-icon="false" class="rule-intro">
          {{ t("collectionDetail.partitionExclusiveHelp") }}
        </NAlert>
        <NFormItem :label="t('collectionDetail.ruleName')" required>
          <NInput
            v-model:value="partitionName"
            :placeholder="t('collectionDetail.partitionNameExample')"
          />
        </NFormItem>
        <NFormItem :label="t('collectionDetail.source')" required>
          <NSelect
            v-model:value="partitionConnectorId"
            :options="scConnectorOptions"
            :placeholder="t('collectionDetail.chooseSource')"
            @update:value="partitionProfileId = null"
          />
        </NFormItem>
        <NFormItem :label="t('collectionDetail.importProfile')" required>
          <NSelect
            v-model:value="partitionProfileId"
            :options="partitionProfileOptions"
            :loading="partitionProfilesQuery.isLoading.value"
            :disabled="!partitionConnectorId || partitionProfileOptions.length === 0"
            :placeholder="t('collectionDetail.chooseProfile')"
          />
        </NFormItem>
        <NFormItem :label="t('collectionDetail.partitionLayer')" required>
          <NInput
            v-model:value="partitionLayerId"
            :placeholder="t('collectionDetail.partitionLayerExample')"
          />
        </NFormItem>
        <div class="rule-condition-row">
          <NFormItem :label="t('collectionDetail.partitionDimension')" required>
            <NSelect v-model:value="partitionDimension" :options="partitionDimensionOptions" />
          </NFormItem>
          <NFormItem :label="t('collectionDetail.partitionValue')" required>
            <NInput
              v-model:value="partitionDimensionValue"
              :placeholder="t('collectionDetail.partitionValueExample')"
            />
          </NFormItem>
        </div>
      </template>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="resetPartitionForm">{{ t("common.cancel") }}</NButton>
          <NButton
            type="primary"
            :disabled="!canCreatePartition"
            :loading="createPartitionMutation.isPending.value"
            @click="createPartitionMutation.mutate()"
          >
            {{ t("collectionDetail.assignPartition") }}
          </NButton>
        </NSpace>
      </template>
    </NModal>

    <NModal
      v-model:show="linkVisible"
      preset="card"
      :title="t('collectionDetail.linkTitle')"
      :style="{ width: 'min(560px, calc(100vw - 32px))' }"
    >
      <template v-if="linkOptions.length > 0">
        <NSelect
          v-model:value="selectedDatasetIds"
          multiple
          filterable
          :options="linkOptions"
          :placeholder="t('collectionDetail.compatibleDatasets')"
        />
        <NAlert v-if="!selectedLinksCompatible" type="error" :show-icon="false">
          {{ t("collectionDetail.sameLabelsRequired") }}
        </NAlert>
      </template>
      <NEmpty v-else :description="t('collectionDetail.noCompatibleDatasets')" />
      <template #footer>
        <NSpace justify="end">
          <NButton @click="linkVisible = false">{{ t("common.cancel") }}</NButton>
          <NButton
            type="primary"
            :disabled="selectedDatasetIds.length === 0 || !selectedLinksCompatible"
            :loading="linkMutation.isPending.value"
            @click="linkMutation.mutate()"
          >
            {{ t("collectionDetail.link") }}
          </NButton>
        </NSpace>
      </template>
    </NModal>

    <NModal
      v-model:show="modelVisible"
      preset="card"
      :title="t('collectionDetail.defaultModel')"
      :style="{ width: 'min(960px, calc(100vw - 32px))' }"
    >
      <NText depth="3">
        {{ t("collectionDetail.modelPickerHelp") }}
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
                {{ t("collectionDetail.clearDefault") }}
              </NButton>
            </template>
            {{ t("collectionDetail.clearDefaultConfirm") }}
          </NPopconfirm>
          <NSpace>
            <NButton @click="modelVisible = false">{{ t("common.cancel") }}</NButton>
            <NButton
              type="primary"
              :disabled="!selectedDefaultModelId"
              :loading="defaultModelMutation.isPending.value"
              @click="defaultModelMutation.mutate(selectedDefaultModelId)"
            >
              {{ t("collectionDetail.saveModel") }}
            </NButton>
          </NSpace>
        </NSpace>
      </template>
    </NModal>

    <NModal
      v-model:show="reconcileVisible"
      preset="card"
      :title="t('collectionDetail.predictTitle')"
      :style="{ width: 'min(560px, calc(100vw - 32px))' }"
    >
      <NAlert type="warning" :show-icon="false">
        {{
          t(
            "collectionDetail.predictConfirm",
            {
              count: selectedCoverage.length,
              model: defaultModel?.name || collection?.default_model_id,
              snapshot: latestReadyRevision ? `r${latestReadyRevision.revision_number}` : "—",
            },
            selectedCoverage.length,
          )
        }}
      </NAlert>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="reconcileVisible = false">{{ t("common.cancel") }}</NButton>
          <NButton
            type="primary"
            :disabled="selectedCoverage.length === 0"
            :loading="reconcileMutation.isPending.value"
            @click="reconcileMutation.mutate()"
          >
            {{ t("collectionDetail.startPrediction") }}
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
