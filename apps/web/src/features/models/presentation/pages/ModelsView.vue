<script setup lang="ts">
import { computed, ref } from "vue";
import { useQueryClient } from "@tanstack/vue-query";
import { useRouter } from "vue-router";
import type { DataTableRowKey } from "naive-ui";
import { NButton, NInput, NModal, NPopconfirm, NSpace, NText, useMessage } from "naive-ui";
import { useI18n } from "vue-i18n";
import {
  deleteModelApiV1ModelsModelIdDelete,
  useDeleteModelApiV1ModelsModelIdDelete,
  useUpdateModelApiV1ModelsModelIdPatch,
} from "@/generated/orval/endpoints/api";
import type { ModelResponse } from "@/generated/orval/models";
import { useAuthStore } from "@/features/auth/application/store";
import { useOrgStore } from "@/features/auth/application/org";
import { orgScopedQueryKey, toUserMessage } from "@/shared/api";
import BulkSelectionToolbar from "@/shared/components/bulk-selection-toolbar/BulkSelectionToolbar.vue";
import { DatasetPageShell, DatasetToolbar } from "@/shared";
import { runBatchAction } from "@/shared/utils/runBatchAction";
import ModelSearchSurface from "../components/ModelSearchSurface.vue";

const message = useMessage();
const { t } = useI18n();
const queryClient = useQueryClient();
const router = useRouter();
const authStore = useAuthStore();
const orgStore = useOrgStore();
const checkedModelIds = ref<DataTableRowKey[]>([]);
const batchDeletePending = ref(false);
const renameVisible = ref(false);
const renameTarget = ref<ModelResponse | null>(null);
const renameName = ref("");

const modelsApiQueryKey = computed(() =>
  orgScopedQueryKey(orgStore.currentOrgId, ["api", "v1", "models"]),
);
const modelsUiQueryKey = computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["models"]));

function invalidateModelQueries(): void {
  void queryClient.invalidateQueries({ queryKey: modelsApiQueryKey.value });
  void queryClient.invalidateQueries({ queryKey: modelsUiQueryKey.value });
}

function modelDisplayName(model: ModelResponse): string {
  return model.name?.trim() || model.id.slice(0, 8);
}

function openModelSource(model: ModelResponse): void {
  if (model.dataset_id) {
    void router.push(`/datasets/${model.dataset_id}`);
    return;
  }
  if (model.collection_id) void router.push(`/dataset-collections/${model.collection_id}`);
}

async function deleteSelectedModels(selectedModels: ModelResponse[]): Promise<void> {
  const selected = selectedModels.filter((model) => model.created_by === authStore.user?.id);
  if (selected.length === 0 || batchDeletePending.value) return;
  if (
    !window.confirm(t("models.confirmDeleteSelected", { count: selected.length }, selected.length))
  ) {
    return;
  }

  batchDeletePending.value = true;
  try {
    const result = await runBatchAction(selected, (model) =>
      deleteModelApiV1ModelsModelIdDelete(model.id),
    );
    checkedModelIds.value = result.failed.map(({ item }) => item.id);
    if (result.succeeded.length > 0) invalidateModelQueries();
    if (result.failed.length === 0) {
      message.success(
        t("models.deletedCount", { count: result.succeeded.length }, result.succeeded.length),
      );
    } else if (result.succeeded.length === 0) {
      message.error(toUserMessage(result.failed[0]?.error, t("models.deleteSelectedFailed")));
    } else {
      message.warning(
        t("models.partialDelete", {
          deleted: result.succeeded.length,
          failed: result.failed.length,
        }),
      );
    }
  } finally {
    batchDeletePending.value = false;
  }
}

const renameMutation = useUpdateModelApiV1ModelsModelIdPatch({
  mutation: {
    onSuccess: () => {
      message.success(t("models.renamed"));
      invalidateModelQueries();
      resetRename();
    },
    onError: (error) => message.error(toUserMessage(error, t("models.renameFailed"))),
  },
});
const deleteMutation = useDeleteModelApiV1ModelsModelIdDelete({
  mutation: {
    onSuccess: () => {
      message.success(t("models.deleted"));
      invalidateModelQueries();
    },
    onError: (error) => message.error(toUserMessage(error, t("models.deleteFailed"))),
  },
});

function openRename(model: ModelResponse): void {
  if (model.created_by !== authStore.user?.id) {
    message.error(t("models.creatorRenameOnly"));
    return;
  }
  renameTarget.value = model;
  renameName.value = modelDisplayName(model);
  renameVisible.value = true;
}

function resetRename(): void {
  renameVisible.value = false;
  renameTarget.value = null;
  renameName.value = "";
}

function submitRename(): false {
  const target = renameTarget.value;
  const name = renameName.value.trim();
  if (!target || !name) return false;
  renameMutation.mutate({ modelId: target.id, data: { name } });
  return false;
}
</script>

<template>
  <DatasetPageShell :is-loading="false" :has-org="!!orgStore.currentOrgId">
    <div class="models-view">
      <DatasetToolbar :title="t('models.title')" />
      <ModelSearchSurface
        v-model:checked-row-keys="checkedModelIds"
        mode="management"
        :active="!!orgStore.currentOrgId"
        :refetch-interval="5000"
        @open-source="openModelSource"
      >
        <template #bulk-actions="{ selectedModels, clearSelection }">
          <BulkSelectionToolbar
            :selected-count="selectedModels.length"
            :item-label="t('models.model')"
            :loading="batchDeletePending"
            @clear="clearSelection"
          >
            <NButton
              size="small"
              type="error"
              :loading="batchDeletePending"
              @click="deleteSelectedModels(selectedModels)"
            >
              {{ t("models.deleteSelected") }}
            </NButton>
          </BulkSelectionToolbar>
        </template>
        <template #row-actions="{ model }">
          <NSpace v-if="model.created_by === authStore.user?.id" :size="6" :wrap="false">
            <NButton size="small" quaternary @click="openRename(model)">
              {{ t("common.rename") }}
            </NButton>
            <NPopconfirm @positive-click="deleteMutation.mutate({ modelId: model.id })">
              <template #trigger>
                <NButton
                  size="small"
                  quaternary
                  type="error"
                  :loading="
                    deleteMutation.isPending.value &&
                    deleteMutation.variables.value?.modelId === model.id
                  "
                >
                  {{ t("common.delete") }}
                </NButton>
              </template>
              {{ t("models.confirmDelete", { name: modelDisplayName(model) }) }}
            </NPopconfirm>
          </NSpace>
          <NText v-else depth="3">—</NText>
        </template>
      </ModelSearchSurface>
    </div>

    <NModal
      v-model:show="renameVisible"
      preset="dialog"
      :title="t('models.renameTitle')"
      :positive-text="t('common.save')"
      :negative-text="t('common.cancel')"
      :loading="renameMutation.isPending.value"
      @positive-click="submitRename"
      @negative-click="resetRename"
    >
      <NInput
        v-model:value="renameName"
        :placeholder="t('models.namePlaceholder')"
        maxlength="255"
        show-count
      />
    </NModal>
  </DatasetPageShell>
</template>

<style scoped>
.models-view {
  height: 100%;
}
</style>
