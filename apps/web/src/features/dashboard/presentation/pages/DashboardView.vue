<template>
  <n-space vertical size="large">
    <template v-if="!orgStore.currentOrgId">
      <div style="padding: 48px; text-align: center">
        <n-empty :description="t('user.noOrganization')" />
      </div>
    </template>
    <template v-else>
      <n-page-header :title="t('dashboard.title')" />

      <n-alert
        v-if="data && !data.prefect_connected"
        type="warning"
        :title="t('dashboard.prefectDisconnected')"
      >
        {{ t("dashboard.prefectDisconnectedDetail") }}
      </n-alert>

      <n-spin :show="isLoading">
        <n-space vertical size="large">
          <n-card
            :title="t('dashboard.workPool')"
            size="small"
            data-testid="dashboard-work-pool-card"
          >
            <template v-if="data?.work_pool">
              <n-space>
                <n-statistic :label="t('dashboard.poolName')" :value="data.work_pool.name" />
                <n-statistic :label="t('dashboard.type')" :value="data.work_pool.type" />
                <n-statistic
                  :label="t('dashboard.slotsUsed')"
                  :value="formatOptionalNumber(data.work_pool.slots_used)"
                />
                <n-statistic
                  :label="t('dashboard.concurrencyLimit')"
                  :value="
                    data.work_pool.concurrency_limit === null
                      ? t('dashboard.unlimited')
                      : formatOptionalNumber(data.work_pool.concurrency_limit)
                  "
                />
              </n-space>
              <n-space style="margin-top: 12px" align="center">
                <span class="stat-label">{{ t("jobs.status") }}</span>
                <n-tag :type="poolStatusType(data.work_pool.status ?? '')" size="small" round>
                  {{ statusLabel(data.work_pool.status ?? "") }}
                </n-tag>
                <span class="stat-label">{{ t("status.paused") }}</span>
                <n-tag :type="data.work_pool.is_paused ? 'warning' : 'success'" size="small" round>
                  {{ data.work_pool.is_paused ? t("dashboard.yes") : t("dashboard.no") }}
                </n-tag>
              </n-space>
            </template>
            <n-alert v-else type="default" :title="t('dashboard.noWorkPool')">
              {{ t("dashboard.noWorkPoolDetail") }}
            </n-alert>
          </n-card>

          <n-card
            :title="t('dashboard.serviceHealth')"
            size="small"
            data-testid="dashboard-service-health-card"
          >
            <n-data-table
              :columns="serviceColumns"
              :data="data?.services ?? []"
              :bordered="true"
              :striped="true"
              size="small"
            />
          </n-card>

          <n-card
            :title="t('dashboard.jobQueue')"
            size="small"
            data-testid="dashboard-job-queue-card"
          >
            <n-grid :cols="5" :x-gap="16" :y-gap="16">
              <n-gi>
                <n-statistic
                  :label="t('status.queued')"
                  :value="formatNumber(data?.job_queue?.queued ?? 0)"
                />
              </n-gi>
              <n-gi>
                <n-statistic
                  :label="t('status.running')"
                  :value="formatNumber(data?.job_queue?.running ?? 0)"
                />
              </n-gi>
              <n-gi>
                <n-statistic
                  :label="t('status.completed')"
                  :value="formatNumber(data?.job_queue?.completed ?? 0)"
                />
              </n-gi>
              <n-gi>
                <n-statistic
                  :label="t('status.failed')"
                  :value="formatNumber(data?.job_queue?.failed ?? 0)"
                />
              </n-gi>
              <n-gi>
                <n-statistic
                  :label="t('status.cancelled')"
                  :value="formatNumber(data?.job_queue?.cancelled ?? 0)"
                />
              </n-gi>
            </n-grid>
          </n-card>

          <n-card
            :title="t('dashboard.recentJobs')"
            size="small"
            data-testid="dashboard-recent-jobs-card"
          >
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
import type { DataTableColumns } from "naive-ui";
import { NTag } from "naive-ui";
import { useI18n } from "vue-i18n";
import { useGetDashboardApiV1DashboardGet } from "@/generated/orval/endpoints/api";
import type { RecentJobSummary, ServiceStatus } from "@/generated/orval/models";
import { useOrgStore } from "@/features/auth/application/org";
import { orgScopedQueryKey } from "@/shared/api";
import { formatDateTime, formatNumber } from "@/shared/i18n/format";

type TagType = "default" | "info" | "success" | "error" | "warning";

const orgStore = useOrgStore();
const { t } = useI18n();

function statusLabel(status: string): string {
  const key = status === "not_ready" ? "status.notReady" : `status.${status}`;
  return status ? t(key) : "—";
}

function formatOptionalNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : formatNumber(value);
}

const { data, isLoading } = useGetDashboardApiV1DashboardGet({
  query: {
    queryKey: computed(() => orgScopedQueryKey(orgStore.currentOrgId, ["dashboard"])),
    refetchInterval: 10000,
    enabled: computed(() => !!orgStore.currentOrgId),
  },
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
    title: t("dashboard.service"),
    key: "name",
    width: 160,
  },
  {
    title: t("dashboard.kind"),
    key: "kind",
    width: 110,
  },
  {
    title: t("jobs.status"),
    key: "status",
    width: 120,
    render: (row) =>
      h(
        NTag,
        { type: serviceStatusType(row.status), size: "small", round: true },
        { default: () => statusLabel(row.status) },
      ),
  },
  {
    title: t("dashboard.latency"),
    key: "latency_ms",
    width: 110,
    render: (row) => (row.latency_ms !== null ? `${row.latency_ms} ms` : "-"),
  },
  {
    title: t("dashboard.detail"),
    key: "detail",
    minWidth: 220,
  },
]);

const columns = computed<DataTableColumns<RecentJobSummary>>(() => [
  {
    title: t("jobs.id"),
    key: "id",
    width: 110,
    render: (row) => row.id.slice(0, 8) + "…",
  },
  {
    title: t("resources.dataset"),
    key: "dataset_id",
    width: 110,
    render: (row) => (row.dataset_id ? row.dataset_id.slice(0, 8) + "…" : t("dashboard.deleted")),
  },
  {
    title: t("jobs.view"),
    key: "trainer_id",
    width: 110,
    render: (row) => row.trainer_id.slice(0, 8) + "…",
  },
  {
    title: t("jobs.status"),
    key: "status",
    width: 120,
    render: (row) =>
      h(
        NTag,
        { type: statusType(row.status), size: "small", round: true },
        { default: () => statusLabel(row.status) },
      ),
  },
  {
    title: t("dashboard.createdBy"),
    key: "created_by",
    width: 120,
  },
  {
    title: t("jobs.createdAt"),
    key: "created_at",
    width: 170,
    render: (row) => formatDateTime(row.created_at),
  },
  {
    title: t("dashboard.updatedAt"),
    key: "updated_at",
    width: 170,
    render: (row) => formatDateTime(row.updated_at),
  },
]);
</script>

<style scoped>
.stat-label {
  font-size: 12px;
  color: var(--n-label-text-color, #888);
}
</style>
