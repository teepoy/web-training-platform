<template>
  <n-modal
    :show="show"
    @update:show="$emit('update:show', $event)"
    preset="dialog"
    :title="isEdit ? 'Edit Subscription' : 'Add Subscription'"
    positive-text="Save"
    negative-text="Cancel"
    :loading="isSaving"
    @positive-click="onSubmit"
    @negative-click="onCancel"
  >
    <n-form
      ref="formRef"
      :model="formModel"
      :rules="formRules"
      label-placement="left"
      label-width="auto"
    >
      <n-form-item label="Workflow Type" path="workflow_type">
        <n-select
          v-model:value="formModel.workflow_type"
          :options="triggerOptions"
          placeholder="Select a workflow type"
          :disabled="isEdit"
        />
      </n-form-item>

      <n-form-item label="Filter Config" path="filter_config">
        <n-space vertical style="width: 100%">
          <n-space v-for="(item, index) in filterPairs" :key="index" align="center" :wrap="false">
            <n-input v-model:value="item.key" placeholder="Key" />
            <n-input v-model:value="item.value" placeholder="Value" />
            <n-button circle size="small" type="error" @click="removeFilter(index)"> X </n-button>
          </n-space>
          <n-button dashed size="small" @click="addFilter"> Add Filter </n-button>
        </n-space>
      </n-form-item>

      <n-form-item label="Enabled" path="enabled">
        <n-switch v-model:value="formModel.enabled" />
      </n-form-item>
    </n-form>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import type { FormInst, FormRules } from "naive-ui";
import {
  useMessage,
  NModal,
  NForm,
  NFormItem,
  NSelect,
  NInput,
  NSpace,
  NButton,
  NSwitch,
} from "naive-ui";
import { useQueryClient } from "@tanstack/vue-query";
import {
  useCreateSensorSubscriptionApiV1SensorsSensorIdSubscriptionsPost,
  useUpdateSensorSubscriptionApiV1SensorsSensorIdSubscriptionsSubIdPatch,
} from "@/generated/orval/endpoints/api";
import { orgScopedQueryKey, toUserMessage } from "@/shared/api";
import { useOrgStore } from "@/features/auth/application/org";
import type {
  SensorDefinitionResponse as SensorDefinition,
  SensorSubscriptionResponse as SensorSubscription,
} from "@/generated/orval/models";

const props = defineProps<{
  show: boolean;
  sensor: SensorDefinition;
  subscription?: SensorSubscription;
}>();

const emit = defineEmits<{
  (e: "update:show", val: boolean): void;
  (e: "saved"): void;
}>();

const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();
const subscriptionsQueryKey = computed(() =>
  orgScopedQueryKey(orgStore.currentOrgId, ["subscriptions", props.sensor.id]),
);
const formRef = ref<FormInst | null>(null);

const isEdit = computed(() => !!props.subscription);

const triggerOptions = computed(() => {
  return props.sensor.available_triggers.map((t) => ({ label: t, value: t }));
});

const formModel = ref({
  workflow_type: null as string | null,
  enabled: true,
});

const filterPairs = ref<{ key: string; value: string }[]>([]);

watch(
  () => props.show,
  (newVal) => {
    if (newVal) {
      if (props.subscription) {
        formModel.value.workflow_type = props.subscription.workflow_type;
        formModel.value.enabled = props.subscription.enabled;

        filterPairs.value = Object.entries(props.subscription.filter_config).map(([k, v]) => ({
          key: k,
          value: String(v),
        }));
      } else {
        formModel.value.workflow_type = props.sensor.available_triggers[0] || null;
        formModel.value.enabled = true;
        filterPairs.value = [];
      }
    }
  },
);

const formRules: FormRules = {
  workflow_type: [
    { required: true, message: "Please select a workflow type", trigger: ["blur", "change"] },
  ],
};

function addFilter() {
  filterPairs.value.push({ key: "", value: "" });
}

function removeFilter(index: number) {
  filterPairs.value.splice(index, 1);
}

const createMutation = useCreateSensorSubscriptionApiV1SensorsSensorIdSubscriptionsPost({
  mutation: {
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: subscriptionsQueryKey.value });
      message.success("Subscription created");
      emit("saved");
      emit("update:show", false);
    },
    onError: (error) => message.error(toUserMessage(error, "Failed to create subscription")),
  },
});

const updateMutation = useUpdateSensorSubscriptionApiV1SensorsSensorIdSubscriptionsSubIdPatch({
  mutation: {
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: subscriptionsQueryKey.value });
      message.success("Subscription updated");
      emit("saved");
      emit("update:show", false);
    },
    onError: (error) => message.error(toUserMessage(error, "Failed to update subscription")),
  },
});

const isSaving = computed(() => createMutation.isPending.value || updateMutation.isPending.value);

function onSubmit() {
  formRef.value?.validate((errors) => {
    if (errors) return;
    if (!formModel.value.workflow_type) return;

    const filterConfig: Record<string, string> = {};
    for (const pair of filterPairs.value) {
      const k = pair.key.trim();
      if (k) {
        filterConfig[k] = pair.value.trim();
      }
    }

    if (isEdit.value) {
      updateMutation.mutate({
        sensorId: props.sensor.id,
        subId: props.subscription!.id,
        data: {
          filter_config: filterConfig,
          enabled: formModel.value.enabled,
        },
      });
    } else {
      createMutation.mutate({
        sensorId: props.sensor.id,
        data: {
          workflow_type: formModel.value.workflow_type!,
          filter_config: filterConfig,
          enabled: formModel.value.enabled,
        },
      });
    }
  });
  return false;
}

function onCancel() {
  emit("update:show", false);
}
</script>
