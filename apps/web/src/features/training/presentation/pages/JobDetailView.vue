<template>
  <n-space vertical size="large">
    <n-page-header :title="job ? job.id : 'Loading…'" @back="goBack">
      <template #subtitle>
        <n-space align="center" :size="8">
          <n-tag v-if="job" :type="statusType(job.status!)" size="small" round>
            {{ job.status }}
          </n-tag>
          <span v-if="job" style="color: var(--n-text-color-3); font-size: 12px">
            by {{ job.created_by }}
          </span>
        </n-space>
      </template>
      <template #extra>
        <n-space>
          <n-tag :type="sseTagType" size="small">
            SSE: {{ sseStatus }}
          </n-tag>
          <n-button
            v-if="job && (job.status === 'running' || job.status === 'queued')"
            type="error"
            size="small"
            :loading="cancelMutation.isPending.value"
            @click="onCancelClick"
          >
            Cancel Job
          </n-button>
        </n-space>
      </template>
    </n-page-header>

    <n-spin v-if="isLoading" size="large" style="display: flex; justify-content: center; padding: 48px 0" />

    <n-alert v-else-if="isError" type="error" :title="(error as Error)?.message ?? 'Failed to load job'" />

    <template v-else-if="job">
      <n-card title="Training Progress" :bordered="true" data-testid="job-training-progress-card">
        <TrainingChart :events="events" :metrics-artifact="metricsArtifact" />
      </n-card>

      <n-card title="Event Log" :bordered="true">
        <n-data-table
          :columns="eventColumns"
          :data="sortedEvents"
          :bordered="false"
          :striped="true"
          size="small"
          :max-height="360"
          :scroll-x="600"
        />
      </n-card>

      <n-card title="Artifacts" :bordered="true">
        <n-empty v-if="!job.artifact_refs || job.artifact_refs.length === 0" description="No artifacts yet" />
        <n-list v-else bordered>
          <n-list-item v-for="artifact in job.artifact_refs" :key="artifact.id">
            <n-space justify="space-between" align="center">
              <n-space vertical :size="2">
                <n-tag size="small" type="info">{{ artifact.kind }}</n-tag>
                <n-text style="font-size: 12px; color: var(--n-text-color-3)">
                  {{ truncateUri(artifact.uri) }}
                </n-text>
              </n-space>
              <n-button
                size="small"
                :loading="downloadingId === artifact.id"
                :disabled="!artifact.id"
                @click="artifact.id ? onDownload(artifact.id) : undefined"
              >
                Download
              </n-button>
            </n-space>
          </n-list-item>
        </n-list>
      </n-card>
    </template>
  </n-space>
</template>

<script setup lang="ts">
import { computed, ref, h } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import { useDialog, useMessage, NTag, NEllipsis } from "naive-ui";
import type { DataTableColumns } from "naive-ui";
import { withAuthQueryParams } from "@/shared/api/client";
import TrainingChart from "@/shared/components/training-chart/TrainingChart.vue";
import { useOrgStore } from '@/features/auth/application/org';
import {
  useGetJobApiV1TrainingJobsJobIdGet,
  useCancelJobApiV1TrainingJobsJobIdCancelPost,
  downloadArtifactApiV1ArtifactsArtifactIdDownloadGet,
  getDownloadArtifactApiV1ArtifactsArtifactIdDownloadGetUrl,
} from "@/generated/orval/endpoints/api";
import type { JobStatus, TrainingJob } from '@/generated/orval/models';
import type { TrainingEvent } from '@/shared/types/components';
import { useJobEvents } from "../../application/useJobEvents";

const route = useRoute();
const router = useRouter();
const dialog = useDialog();
const message = useMessage();
const qc = useQueryClient();
const orgStore = useOrgStore();

const id = computed(() => route.params.id as string);

const {
  data: job,
  isLoading,
  isError,
  error,
} = useGetJobApiV1TrainingJobsJobIdGet(id, {
  query: {
    select: (response) => response.data as TrainingJob,
    queryKey: computed(() => ["jobs", id.value]),
    refetchInterval: 5000,
  },
});

const returnPath = computed(() => {
  const raw = route.query.from;
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (isUsableReturnPath(value)) return value;
  const historyBack = window.history.state?.back;
  if (isUsableReturnPath(historyBack)) return historyBack;
  return "/jobs";
});

function goBack() {
  router.push(returnPath.value);
}

function isUsableReturnPath(value: unknown): value is string {
  return typeof value === "string" && value.startsWith("/") && !value.startsWith(route.path);
}

const metricsArtifactRef = computed(() =>
  job.value?.artifact_refs?.find((artifact: { kind: string }) => artifact.kind === "metrics") ?? null,
);

const { data: metricsArtifact } = useQuery({
  queryKey: computed(() => ["job-metrics-artifact", id.value, metricsArtifactRef.value?.id ?? null]),
  queryFn: async () => {
    const artifact = metricsArtifactRef.value;
    if (!artifact || !artifact.id) {
      return null;
    }
    const resp = await downloadArtifactApiV1ArtifactsArtifactIdDownloadGet(artifact.id);
    return resp.data as Record<string, unknown> | null;
  },
  enabled: computed(() => !!metricsArtifactRef.value?.id && !!orgStore.currentOrgId),
});

const { events, status: sseStatus } = useJobEvents(id);

type TagType = "default" | "info" | "success" | "error" | "warning";

function statusType(status: JobStatus): TagType {
  const map: Record<JobStatus, TagType> = {
    queued: "default",
    running: "info",
    completed: "success",
    failed: "error",
    cancelled: "warning",
  };
  return map[status] ?? "default";
}

const sseTagType = computed<TagType>(() => {
  switch (sseStatus.value) {
    case "connecting":
      return "info";
    case "open":
      return "success";
    case "closed":
      return "default";
    case "error":
      return "error";
    default:
      return "default";
  }
});

const sortedEvents = computed<TrainingEvent[]>(() =>
  [...events.value].sort((a, b) => {
    if (a.ts < b.ts) return 1;
    if (a.ts > b.ts) return -1;
    return 0;
  }),
);

type LevelTagType = "default" | "info" | "success" | "error" | "warning";

function levelType(level: string): LevelTagType {
  switch (level.toLowerCase()) {
    case "info":
      return "info";
    case "warn":
    case "warning":
      return "warning";
    case "error":
      return "error";
    case "debug":
      return "default";
    default:
      return "default";
  }
}

function truncateJson(obj: Record<string, unknown>, maxLen = 80): string {
  const str = JSON.stringify(obj);
  return str.length > maxLen ? str.slice(0, maxLen) + "…" : str;
}

function truncateUri(uri: string, maxLen = 60): string {
  return uri.length > maxLen ? "…" + uri.slice(-maxLen) : uri;
}

const eventColumns = computed<DataTableColumns<TrainingEvent>>(() => [
  {
    title: "Timestamp",
    key: "ts",
    width: 190,
    render: (row) => new Date(row.ts).toLocaleString(),
  },
  {
    title: "Level",
    key: "level",
    width: 90,
    render: (row) =>
      h(
        NTag,
        { type: levelType(row.level), size: "small", round: true },
        { default: () => row.level },
      ),
  },
  {
    title: "Message",
    key: "message",
    ellipsis: { tooltip: true },
  },
  {
    title: "Payload",
    key: "payload",
    width: 260,
    render: (row) =>
      h(
        NEllipsis,
        { style: "max-width: 240px; font-size: 11px; font-family: monospace" },
        { default: () => truncateJson(row.payload) },
      ),
  },
]);

const cancelMutation = useCancelJobApiV1TrainingJobsJobIdCancelPost({
  mutation: {
    onSuccess: () => {
      message.success("Job cancelled");
      qc.invalidateQueries({ queryKey: ["jobs", id.value] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (err: Error) => {
      message.error(err.message ?? "Failed to cancel job");
    },
  },
});

function onCancelClick() {
  dialog.warning({
    title: "Confirm",
    content: "Are you sure you want to cancel this job? This action cannot be undone.",
    positiveText: "Cancel Job",
    negativeText: "Go Back",
    onPositiveClick: () => {
      cancelMutation.mutate({ jobId: id.value });
    },
  });
}

const downloadingId = ref<string | null>(null);

async function onDownload(artifactId: string) {
  downloadingId.value = artifactId;
  try {
    const downloadUrl = withAuthQueryParams(
      getDownloadArtifactApiV1ArtifactsArtifactIdDownloadGetUrl(artifactId)
    );
    window.open(downloadUrl, "_blank");
  } catch (err) {
    message.error((err as Error)?.message ?? "Download failed");
  } finally {
    downloadingId.value = null;
  }
}
</script>
