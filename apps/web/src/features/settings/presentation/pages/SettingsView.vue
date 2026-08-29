<template>
  <n-space vertical size="large">
    <h1>{{ t("settings.title") }}</h1>

    <div class="section-header">
      <h2>{{ t("settings.accessKeys") }}</h2>
      <n-button type="primary" @click="openCreateModal">{{
        t("settings.createAccessKey")
      }}</n-button>
    </div>

    <n-alert v-if="isError" type="error" :title="t('settings.failedToLoad')">
      {{ error?.message ?? t("common.unexpectedError") }}
      <template #footer>
        <n-button size="small" @click="refetch()">{{ t("common.retry") }}</n-button>
      </template>
    </n-alert>

    <n-empty
      v-if="!isLoading && !isError && (tokens?.length ?? 0) === 0"
      :description="t('settings.noKeys')"
    >
      <template #extra>
        <n-button type="primary" @click="openCreateModal">{{
          t("settings.createFirstKey")
        }}</n-button>
      </template>
    </n-empty>

    <n-spin :show="isLoading">
      <n-data-table
        :columns="columns"
        :data="tokens ?? []"
        :loading="isLoading"
        :bordered="false"
      />
    </n-spin>

    <n-modal
      v-model:show="showModal"
      preset="dialog"
      :title="modalStep === 'form' ? t('settings.createAccessKey') : t('settings.accessKeyCreated')"
      :positive-text="modalStep === 'form' ? t('common.create') : t('common.done')"
      :negative-text="t('common.cancel')"
      :loading="modalStep === 'form' && createMutation.isPending.value"
      @positive-click="onModalPositive"
      @negative-click="onCancel"
    >
      <template v-if="modalStep === 'form'">
        <n-form
          ref="formRef"
          :model="formModel"
          :rules="formRules"
          label-placement="left"
          label-width="auto"
        >
          <n-form-item :label="t('common.name')" path="name">
            <n-input v-model:value="formModel.name" placeholder="my-access-key" :maxlength="100" />
          </n-form-item>
        </n-form>
      </template>

      <template v-else>
        <div class="created-token-display">
          <label class="created-token-label">{{ t("settings.accessKey") }}</label>
          <n-input :value="createdToken" readonly />
        </div>
        <n-button class="copy-btn" @click="copyToken">{{ t("common.copy") }}</n-button>
        <n-alert type="warning">
          {{ t("settings.copyWarning") }}
        </n-alert>
      </template>
    </n-modal>
  </n-space>
</template>

<script setup lang="ts">
import { ref, computed, h } from "vue";
import { useQueryClient } from "@tanstack/vue-query";
import type { DataTableColumns, FormInst, FormRules } from "naive-ui";
import { useMessage, NButton, NPopconfirm } from "naive-ui";
import {
  useCreateTokenApiV1AuthTokensPost,
  useListTokensApiV1AuthTokensGet,
  useDeleteTokenApiV1AuthTokensTokenIdDelete,
} from "@/generated/orval/endpoints/api";
import { toUserMessage } from "@/shared/api";
import type { PersonalAccessToken } from "@/shared/api/types";
import { useI18n } from "vue-i18n";

const authKeys = {
  tokens: ["auth", "tokens"] as const,
};

const message = useMessage();
const qc = useQueryClient();
const { d, t } = useI18n();

const {
  data: tokens,
  isLoading,
  isError,
  error,
  refetch,
} = useListTokensApiV1AuthTokensGet({
  query: {
    queryKey: authKeys.tokens,
  },
});

const createdToken = ref("");

const createMutation = useCreateTokenApiV1AuthTokensPost({
  mutation: {
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: authKeys.tokens });
      message.success(t("settings.createdSuccess"));
      createdToken.value = result.token;
      modalStep.value = "created";
    },
    onError: (error) => message.error(toUserMessage(error, t("settings.saveFailed"))),
  },
});

const deleteMutation = useDeleteTokenApiV1AuthTokensTokenIdDelete({
  mutation: {
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: authKeys.tokens });
      message.success(t("settings.deletedSuccess"));
    },
    onError: (error) => message.error(toUserMessage(error, t("settings.deleteFailed"))),
  },
});

const columns = computed<DataTableColumns<PersonalAccessToken>>(() => [
  {
    title: t("common.name"),
    key: "name",
    ellipsis: { tooltip: true },
  },
  {
    title: t("settings.prefix"),
    key: "token_prefix",
  },
  {
    title: t("settings.created"),
    key: "created_at",
    render: (row) => d(new Date(row.created_at), "short"),
  },
  {
    title: t("common.actions"),
    key: "actions",
    width: 100,
    render: (row) =>
      h(
        NPopconfirm,
        {
          onPositiveClick: (e: MouseEvent) => {
            e.stopPropagation();
            deleteMutation.mutate({ tokenId: row.id });
          },
        },
        {
          trigger: () =>
            h(
              NButton,
              {
                size: "small",
                type: "error",
                loading: deleteMutation.isPending.value,
                onClick: (e: Event) => e.stopPropagation(),
              },
              { default: () => t("common.delete") },
            ),
          default: () => t("settings.confirmDelete"),
        },
      ),
  },
]);

const showModal = ref(false);
const modalStep = ref<"form" | "created">("form");
const formRef = ref<FormInst | null>(null);

const formModel = ref({
  name: "",
});

const formRules = computed<FormRules>(() => ({
  name: [
    {
      required: true,
      message: t("common.required", { field: t("common.name") }),
      trigger: ["blur", "input"],
    },
    { whitespace: true, message: t("settings.nameEmpty"), trigger: ["blur"] },
  ],
}));

function openCreateModal() {
  resetForm();
  showModal.value = true;
}

function onModalPositive() {
  if (modalStep.value === "form") {
    formRef.value?.validate((errors) => {
      if (errors) return;
      createMutation.mutate({ data: { name: formModel.value.name } });
    });
    return false;
  }
  showModal.value = false;
  resetForm();
}

function onCancel() {
  showModal.value = false;
  resetForm();
}

function resetForm() {
  formModel.value.name = "";
  createdToken.value = "";
  modalStep.value = "form";
  formRef.value?.restoreValidation();
}

async function copyToken() {
  try {
    await navigator.clipboard.writeText(createdToken.value);
    message.success(t("common.copied"));
  } catch {
    message.error(t("settings.copyFailed"));
  }
}
</script>

<style scoped>
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header h2 {
  margin: 0;
}

.created-token-display {
  margin-bottom: 16px;
}

.created-token-label {
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
  font-weight: 500;
}

.copy-btn {
  margin-bottom: 16px;
}
</style>
