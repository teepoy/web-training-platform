<template>
  <n-space vertical size="large">
    <template v-if="!orgStore.currentOrgId">
      <div style="padding: 48px; text-align: center;">
        <n-empty description="You are not a member of any organization. Contact an admin." />
      </div>
    </template>
    <template v-else>
    <n-page-header title="Dashboard" />

    <n-alert v-if="data && !data.prefect_connected" type="warning" title="Prefect not connected">
      Work pool and schedule data may be unavailable. Check your Prefect API configuration.
    </n-alert>

    <n-spin :show="isLoading">
      <n-space vertical size="large">
        <n-card title="Work Pool" size="small">
          <template v-if="data?.work_pool">
            <n-space>
              <n-statistic label="Pool Name" :value="data.work_pool.name" />
              <n-statistic label="Type" :value="data.work_pool.type" />
              <n-statistic label="Slots Used" :value="String(data.work_pool.slots_used)" />
              <n-statistic
                label="Concurrency Limit"
                :value="data.work_pool.concurrency_limit !== null ? String(data.work_pool.concurrency_limit) : 'Unlimited'"
              />
            </n-space>
            <n-space style="margin-top: 12px" align="center">
              <span class="stat-label">Status</span>
              <n-tag :type="poolStatusType(data.work_pool.status)" size="small" round>
                {{ data.work_pool.status }}
              </n-tag>
              <span class="stat-label">Paused</span>
              <n-tag :type="data.work_pool.is_paused ? 'warning' : 'success'" size="small" round>
                {{ data.work_pool.is_paused ? 'Yes' : 'No' }}
              </n-tag>
            </n-space>
          </template>
          <n-alert v-else type="default" title="No work pool data">
            Work pool information is unavailable.
          </n-alert>
        </n-card>

        <n-card title="Service Health" size="small">
          <n-data-table
            :columns="serviceColumns"
            :data="data?.services ?? []"
            :bordered="true"
            :striped="true"
            size="small"
          />
        </n-card>

        <n-card title="Job Queue" size="small">
          <n-grid :cols="5" :x-gap="16" :y-gap="16">
            <n-gi>
              <n-statistic label="Queued" :value="String(data?.job_queue.queued ?? 0)" />
            </n-gi>
            <n-gi>
              <n-statistic label="Running" :value="String(data?.job_queue.running ?? 0)" />
            </n-gi>
            <n-gi>
              <n-statistic label="Completed" :value="String(data?.job_queue.completed ?? 0)" />
            </n-gi>
            <n-gi>
              <n-statistic label="Failed" :value="String(data?.job_queue.failed ?? 0)" />
            </n-gi>
            <n-gi>
              <n-statistic label="Cancelled" :value="String(data?.job_queue.cancelled ?? 0)" />
            </n-gi>
          </n-grid>
        </n-card>

        <n-card title="Recent Jobs" size="small">
          <n-data-table
            :columns="columns"
            :data="data?.recent_jobs ?? []"
            :bordered="true"
            :striped="true"
            :loading="isLoading"
            size="small"
          />
        </n-card>
      </n-space>
    </n-spin>
    </template>
  </n-space>
</template>

<script setup lang="ts">
import { computed, h } from "vue";
import { useQuery } from "@tanstack/vue-query";
import type { DataTableColumns } from "naive-ui";
import { NTag } from "naive-ui";
import { api } from "../api";
import type { RecentJobSummary, ServiceStatus } from "../types";
import { useOrgStore } from "../stores/org";

type TagType = "default" | "info" | "success" | "error" | "warning";

const orgStore = useOrgStore();

const { data, isLoading } = useQuery({
  queryKey: computed(() => ["dashboard", orgStore.currentOrgId]),
  queryFn: () => api.getDashboard(),
  refetchInterval: 10000,
  enabled: computed(() => !!orgStore.currentOrgId),
});

function statusType(status: string): TagType {
  const map: Record<string, TagType> = {
    queued: "default",
    running: "info",
    completed: "success",
    failed: "error",
    cancelled: "warning",
  };
  return map[status] ?? "default";
}

function poolStatusType(status: string): TagType {
  const map: Record<string, TagType> = {
    ready: "success",
    not_ready: "warning",
    paused: "warning",
    offline: "error",
  };
  return map[status] ?? "default";
}

function serviceStatusType(status: string): TagType {
  const map: Record<string, TagType> = {
    healthy: "success",
    degraded: "warning",
    down: "error",
  };
  return map[status] ?? "default";
}

const serviceColumns = computed<DataTableColumns<ServiceStatus>>(() => [
  {
    title: "Service",
    key: "name",
    width: 160,
  },
  {
    title: "Kind",
    key: "kind",
    width: 110,
  },
  {
    title: "Status",
    key: "status",
    width: 120,
    render: (row) =>
      h(
        NTag,
        { type: serviceStatusType(row.status), size: "small", round: true },
        { default: () => row.status }
      ),
  },
  {
    title: "Latency",
    key: "latency_ms",
    width: 110,
    render: (row) => row.latency_ms !== null ? `${row.latency_ms} ms` : "-",
  },
  {
    title: "Detail",
    key: "detail",
    minWidth: 220,
  },
]);

const columns = computed<DataTableColumns<RecentJobSummary>>(() => [
  {
    title: "ID",
    key: "id",
    width: 110,
    render: (row) => row.id.slice(0, 8) + "…",
  },
  {
    title: "Dataset",
    key: "dataset_id",
    width: 110,
    render: (row) => row.dataset_id.slice(0, 8) + "…",
  },
  {
    title: "Preset",
    key: "preset_id",
    width: 110,
    render: (row) => row.preset_id.slice(0, 8) + "…",
  },
  {
    title: "Status",
    key: "status",
    width: 120,
    render: (row) =>
      h(
        NTag,
        { type: statusType(row.status), size: "small", round: true },
        { default: () => row.status }
      ),
  },
  {
    title: "Created By",
    key: "created_by",
    width: 120,
  },
  {
    title: "Created At",
    key: "created_at",
    width: 170,
    render: (row) => new Date(row.created_at).toLocaleString(),
  },
  {
    title: "Updated At",
    key: "updated_at",
    width: 170,
    render: (row) => new Date(row.updated_at).toLocaleString(),
  },
]);
</script>

<style scoped>
.stat-label {
  font-size: 12px;
  color: var(--n-label-text-color, #888);
}
</style>
