<template>
  <n-space vertical size="large">
    <n-page-header title="Sensor Subscriptions" />

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
        <n-card :title="selectedSensor ? `Subscriptions: ${selectedSensor.name}` : 'Subscriptions'" :bordered="false" size="small">
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
import { useQuery, useMutation, useQueryClient } from "@tanstack/vue-query";
import type { DataTableColumns } from "naive-ui";
import { useMessage, NPageHeader, NSpace, NGrid, NGridItem, NCard, NDataTable, NSpin, NEmpty, NButton, NSwitch, NPopconfirm, NTag } from "naive-ui";
import { listSensors, listSubscriptions, updateSubscription, deleteSubscription } from "@platform/web-ui/api/sensors";
import type { SensorDefinition, SensorSubscription } from "@platform/web-ui/api/types";
import SensorSubscriptionModal from "./SensorSubscriptionModal.vue";

const message = useMessage();
const qc = useQueryClient();

const selectedSensorId = ref<string | null>(null);

// ---------------------------------------------------------------------------
// Sensors List
// ---------------------------------------------------------------------------
const { data: sensors, isLoading: isLoadingSensors } = useQuery({
  queryKey: ["sensors"],
  queryFn: listSensors,
});

const selectedSensor = computed(() => {
  return sensors.value?.find(s => s.id === selectedSensorId.value) || null;
});

const sensorColumns = computed<DataTableColumns<SensorDefinition>>(() => [
  {
    title: "Name",
    key: "name",
    render: (row) => h(
      "div",
      { style: selectedSensorId.value === row.id ? "font-weight: bold; color: var(--n-text-color-pressed);" : "" },
      row.name
    )
  },
  {
    title: "Cron",
    key: "cron",
  }
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
const { data: subscriptions, isLoading: isLoadingSubscriptions } = useQuery({
  queryKey: computed(() => ["subscriptions", selectedSensorId.value]),
  queryFn: () => listSubscriptions(selectedSensorId.value!),
  enabled: computed(() => !!selectedSensorId.value),
});

const toggleMutation = useMutation({
  mutationFn: ({ subId, enabled }: { subId: string, enabled: boolean }) =>
    updateSubscription(selectedSensorId.value!, subId, { enabled }),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["subscriptions", selectedSensorId.value] });
    message.success("Subscription updated");
  },
  onError: (err: Error) => message.error(err.message ?? "Failed to update subscription"),
});

const deleteMutation = useMutation({
  mutationFn: (subId: string) => deleteSubscription(selectedSensorId.value!, subId),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["subscriptions", selectedSensorId.value] });
    message.success("Subscription deleted");
  },
  onError: (err: Error) => message.error(err.message ?? "Failed to delete subscription"),
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
      if (keys.length === 0) return h(NTag, { size: "small", type: "info" }, { default: () => "Match All" });
      return h("pre", { style: "margin: 0; font-size: 12px; white-space: pre-wrap;" }, JSON.stringify(row.filter_config, null, 2));
    }
  },
  {
    title: "Enabled",
    key: "enabled",
    width: 100,
    render: (row) => h(
      NSwitch,
      {
        value: row.enabled,
        onUpdateValue: (val: boolean) => toggleMutation.mutate({ subId: row.id, enabled: val })
      }
    )
  },
  {
    title: "Actions",
    key: "actions",
    width: 150,
    render: (row) => h(NSpace, { size: "small" }, {
      default: () => [
        h(
          NButton,
          {
            size: "small",
            onClick: () => openEditModal(row),
          },
          { default: () => "Edit" }
        ),
        h(
          NPopconfirm,
          {
            onPositiveClick: () => deleteMutation.mutate(row.id),
          },
          {
            trigger: () => h(
              NButton,
              { size: "small", type: "error" },
              { default: () => "Delete" }
            ),
            default: () => "Are you sure?"
          }
        )
      ]
    })
  }
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
