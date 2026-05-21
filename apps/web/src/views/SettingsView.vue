<template>
  <n-space vertical size="large">
    <h1>Settings</h1>

    <div class="section-header">
      <h2>Access Keys</h2>
      <n-button type="primary" @click="openCreateModal">Create Access Key</n-button>
    </div>

    <!-- Error state -->
    <n-alert v-if="isError" type="error" title="Failed to load access keys">
      {{ error?.message ?? "An unexpected error occurred." }}
      <template #footer>
        <n-button size="small" @click="refetch()">Retry</n-button>
      </template>
    </n-alert>

    <!-- Empty state -->
    <n-empty
      v-if="!isLoading && !isError && (tokens?.length ?? 0) === 0"
      description="No access keys yet"
    >
      <template #extra>
        <n-button type="primary" @click="openCreateModal">
          Create your first key
        </n-button>
      </template>
    </n-empty>

    <!-- Data table -->
    <n-spin :show="isLoading">
      <n-data-table
        :columns="columns"
        :data="tokens ?? []"
        :loading="isLoading"
        :bordered="false"
      />
    </n-spin>

    <!-- Create Modal -->
    <n-modal
      v-model:show="showModal"
      preset="dialog"
      :title="modalStep === 'form' ? 'Create Access Key' : 'Access Key Created'"
      :positive-text="modalStep === 'form' ? 'Create' : 'Done'"
      negative-text="Cancel"
      :loading="modalStep === 'form' && createMutation.isPending.value"
      @positive-click="onModalPositive"
      @negative-click="onCancel"
    >
      <!-- Form state -->
      <template v-if="modalStep === 'form'">
        <n-form
          ref="formRef"
          :model="formModel"
          :rules="formRules"
          label-placement="left"
          label-width="auto"
        >
          <n-form-item label="Name" path="name">
            <n-input
              v-model:value="formModel.name"
              placeholder="my-access-key"
              :maxlength="100"
            />
          </n-form-item>
        </n-form>
      </template>

      <!-- Created state -->
      <template v-else>
        <div class="created-token-display">
          <label class="created-token-label">Access Key</label>
          <n-input :value="createdToken" readonly />
        </div>
        <n-button @click="copyToken" class="copy-btn">
          Copy
        </n-button>
        <n-alert type="warning">
          Copy your access key now. You won't be able to see it again.
        </n-alert>
      </template>
    </n-modal>
  </n-space>
</template>

<script setup lang="ts">
import { ref, computed, h } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import type { DataTableColumns, FormInst, FormRules } from "naive-ui";
import { useMessage, NButton, NPopconfirm } from "naive-ui";
import {
  createToken,
  listTokens,
  deleteToken,
  authKeys,
} from "@/shared/api";
import type {
  PersonalAccessToken,
  PersonalAccessTokenCreated,
} from "@/shared/api";

const message = useMessage();
const qc = useQueryClient();

// ---------------------------------------------------------------------------
// Query
// ---------------------------------------------------------------------------

const {
  data: tokens,
  isLoading,
  isError,
  error,
  refetch,
} = useQuery({
  queryKey: authKeys.tokens,
  queryFn: listTokens,
});

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

const createdToken = ref("");

const createMutation = useMutation({
  mutationFn: (name: string) => createToken(name),
  onSuccess: (data: PersonalAccessTokenCreated) => {
    qc.invalidateQueries({ queryKey: authKeys.tokens });
    message.success("Access key created");
    createdToken.value = data.token;
    modalStep.value = "created";
  },
  onError: (err: Error) => message.error(err.message),
});

const deleteMutation = useMutation({
  mutationFn: (id: string) => deleteToken(id),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: authKeys.tokens });
    message.success("Access key deleted");
  },
  onError: (err: Error) => message.error(err.message),
});

// ---------------------------------------------------------------------------
// Table columns
// ---------------------------------------------------------------------------

const columns = computed<DataTableColumns<PersonalAccessToken>>(() => [
  {
    title: "Name",
    key: "name",
    ellipsis: { tooltip: true },
  },
  {
    title: "Prefix",
    key: "token_prefix",
  },
  {
    title: "Created",
    key: "created_at",
    render: (row) => new Date(row.created_at).toLocaleDateString(),
  },
  {
    title: "Actions",
    key: "actions",
    width: 100,
    render: (row) =>
      h(
        NPopconfirm,
        {
          onPositiveClick: (e: MouseEvent) => {
            e.stopPropagation();
            deleteMutation.mutate(row.id);
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
              { default: () => "Delete" }
            ),
          default: () =>
            "Are you sure you want to delete this access key? Any applications using it will lose access.",
        }
      ),
  },
]);

// ---------------------------------------------------------------------------
// Modal / form
// ---------------------------------------------------------------------------

const showModal = ref(false);
const modalStep = ref<"form" | "created">("form");
const formRef = ref<FormInst | null>(null);

const formModel = ref({
  name: "",
});

const formRules: FormRules = {
  name: [
    { required: true, message: "Name is required", trigger: ["blur", "input"] },
    { whitespace: true, message: "Name cannot be empty", trigger: ["blur"] },
  ],
};

function openCreateModal() {
  resetForm();
  showModal.value = true;
}

function onModalPositive() {
  if (modalStep.value === "form") {
    formRef.value?.validate((errors) => {
      if (errors) return;
      createMutation.mutate(formModel.value.name);
    });
    return false;
  }
  // "created" state — close and reset
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
    message.success("Copied!");
  } catch {
    message.error("Failed to copy");
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
