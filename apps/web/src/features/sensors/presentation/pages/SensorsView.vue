<template>
  <n-space vertical size="large">
    <n-page-header title="Automations" />

    <n-grid :x-gap="24" :y-gap="24" cols="1 s:1 m:2 l:3" responsive="screen">
      <!-- Left Column: Sensors -->
      <n-grid-item span="1">
        <n-card title="Sensors" :bordered="false" size="small">
          <n-spin :show="isLoadingSensors">
            <n-data-table
              :columns="sensorColumns"
              :data="sensors ?? []"
              :row-props="sensorRowProps"
              :bordered="true"
              :loading="isLoadingSensors"
            />
          </n-spin>
        </n-card>
      </n-grid-item>

      <!-- Right Column: Subscriptions -->
      <n-grid-item span="1 s:1 m:1 l:2">
        <n-card
          :title="selectedSensor ? `Subscriptions: ${selectedSensor.name}` : 'Subscriptions'"
          :bordered="false"
          size="small"
        >
          <template #header-extra>
            <n-button
              type="primary"
              size="small"
              :disabled="!selectedSensor"
              @click="openCreateModal"
            >
              Add Subscription
            </n-button>
          </template>

          <template v-if="!selectedSensor">
            <n-empty description="Select a sensor to view subscriptions" />
          </template>
          <template v-else>
            <n-spin :show="isLoadingSubscriptions">
              <n-data-table
                :columns="subscriptionColumns"
                :data="subscriptions ?? []"
                :bordered="true"
                :striped="true"
                :loading="isLoadingSubscriptions"
              />
            </n-spin>
          </template>
        </n-card>
      </n-grid-item>
    </n-grid>

    <SensorSubscriptionModal
      v-if="selectedSensor"
      v-model:show="showModal"
      :sensor="selectedSensor"
      :subscription="editingSubscription"
      @saved="onModalSaved"
    />
  </n-space>
</template>

<script setup lang="ts">
import { ref, computed, h } from "vue";
import { useQueryClient } from "@tanstack/vue-query";
import type { DataTableColumns } from "naive-ui";
import {
  useMessage,
  NPageHeader,
  NSpace,
  NGrid,
  NGridItem,
  NCard,
  NDataTable,
  NSpin,
  NEmpty,
  NButton,
  NSwitch,
  NPopconfirm,
  NTag,
} from "naive-ui";
import {
  useListSensorsApiV1SensorsGet,
  useListSensorSubscriptionsApiV1SensorsSensorIdSubscriptionsGet,
  useUpdateSensorSubscriptionApiV1SensorsSensorIdSubscriptionsSubIdPatch,
  useDeleteSensorSubscriptionApiV1SensorsSensorIdSubscriptionsSubIdDelete,
} from "@/generated/orval/endpoints/api";
import { orgScopedQueryKey, toUserMessage } from "@/shared/api";
import { useOrgStore } from "@/features/auth/application/org";
import type {
  SensorDefinitionResponse as SensorDefinition,
  SensorSubscriptionResponse as SensorSubscription,
} from "@/generated/orval/models";
import SensorSubscriptionModal from "./SensorSubscriptionModal.vue";

const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();

const selectedSensorId = ref<string | null>(null);

// ---------------------------------------------------------------------------
// Sensors List
// ---------------------------------------------------------------------------
const { data: sensors, isLoading: isLoadingSensors } = useListSensorsApiV1SensorsGet({
  query: {
    queryKey: computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["sensors"])),
    enabled: computed(() => !!orgStore.currentOrgId),
  },
});

const selectedSensor = computed(() => {
  return sensors.value?.find((s) => s.id === selectedSensorId.value) || null;
});

const sensorColumns = computed<DataTableColumns<SensorDefinition>>(() => [
  {
    title: "Name",
    key: "name",
    render: (row) =>
      h(
        "div",
        {
          style:
            selectedSensorId.value === row.id
              ? "font-weight: bold; color: var(--n-text-color-pressed);"
              : "",
        },
        row.name,
      ),
  },
  {
    title: "Cron",
    key: "cron",
  },
]);

function sensorRowProps(row: SensorDefinition) {
  return {
    style: "cursor: pointer",
    onClick: () => {
      selectedSensorId.value = row.id;
    },
  };
}

// ---------------------------------------------------------------------------
// Subscriptions List
// ---------------------------------------------------------------------------
const sensorId = computed(() => selectedSensorId.value ?? "");
const subscriptionsQueryKey = computed(() =>
  orgScopedQueryKey(orgStore.currentOrgId, ["subscriptions", selectedSensorId.value]),
);

const { data: subscriptions, isLoading: isLoadingSubscriptions } =
  useListSensorSubscriptionsApiV1SensorsSensorIdSubscriptionsGet(sensorId, {
    query: {
      queryKey: subscriptionsQueryKey,
      enabled: computed(() => !!orgStore.currentOrgId && !!selectedSensorId.value),
    },
  });

const toggleMutation = useUpdateSensorSubscriptionApiV1SensorsSensorIdSubscriptionsSubIdPatch({
  mutation: {
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: subscriptionsQueryKey.value });
      message.success("Subscription updated");
    },
    onError: (error) => message.error(toUserMessage(error, "Failed to update subscription")),
  },
});

const deleteMutation = useDeleteSensorSubscriptionApiV1SensorsSensorIdSubscriptionsSubIdDelete({
  mutation: {
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: subscriptionsQueryKey.value });
      message.success("Subscription deleted");
    },
    onError: (error) => message.error(toUserMessage(error, "Failed to delete subscription")),
  },
});

const subscriptionColumns = computed<DataTableColumns<SensorSubscription>>(() => [
  {
    title: "Workflow Type",
    key: "workflow_type",
  },
  {
    title: "Filter Config",
    key: "filter_config",
    render: (row) => {
      const keys = Object.keys(row.filter_config);
      if (keys.length === 0)
        return h(NTag, { size: "small", type: "info" }, { default: () => "Match All" });
      return h(
        "pre",
        { style: "margin: 0; font-size: 12px; white-space: pre-wrap;" },
        JSON.stringify(row.filter_config, null, 2),
      );
    },
  },
  {
    title: "Enabled",
    key: "enabled",
    width: 100,
    render: (row) =>
      h(NSwitch, {
        value: row.enabled,
        onUpdateValue: (val: boolean) =>
          toggleMutation.mutate({
            sensorId: selectedSensorId.value!,
            subId: row.id,
            data: { enabled: val },
          }),
      }),
  },
  {
    title: "Actions",
    key: "actions",
    width: 150,
    render: (row) =>
      h(
        NSpace,
        { size: "small" },
        {
          default: () => [
            h(
              NButton,
              {
                size: "small",
                onClick: () => openEditModal(row),
              },
              { default: () => "Edit" },
            ),
            h(
              NPopconfirm,
              {
                onPositiveClick: () =>
                  deleteMutation.mutate({ sensorId: selectedSensorId.value!, subId: row.id }),
              },
              {
                trigger: () =>
                  h(NButton, { size: "small", type: "error" }, { default: () => "Delete" }),
                default: () => "Are you sure?",
              },
            ),
          ],
        },
      ),
  },
]);

// ---------------------------------------------------------------------------
// Modal Management
// ---------------------------------------------------------------------------
const showModal = ref(false);
const editingSubscription = ref<SensorSubscription | undefined>(undefined);

function openCreateModal() {
  editingSubscription.value = undefined;
  showModal.value = true;
}

function openEditModal(sub: SensorSubscription) {
  editingSubscription.value = sub;
  showModal.value = true;
}

function onModalSaved() {
  // Queries are already invalidated by the modal's mutation onSuccess
}
</script>
