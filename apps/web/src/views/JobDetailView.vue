<template>
  <n-space vertical size="large">
    <!-- Header -->
    <n-page-header :title="job ? job.id : 'Loading…'" @back="router.push('/jobs')">
      <template #subtitle>
        <n-space align="center" :size="8">
          <n-tag v-if="job" :type="statusType(job.status)" size="small" round>
            {{ job.status }}
          </n-tag>
          <span v-if="job" style="color: var(--n-text-color-3); font-size: 12px">
            by {{ job.created_by }}
          </span>
        </n-space>
      </template>
      <template #extra>
        <n-space>
          <!-- SSE connection status badge -->
          <n-tag :type="sseTagType" size="small">
            SSE: {{ sseStatus }}
          </n-tag>
          <!-- Cancel button — only shown when job is active -->
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

    <!-- Loading / error states -->
    <n-spin v-if="isLoading" size="large" style="display: flex; justify-content: center; padding: 48px 0" />

    <n-alert v-else-if="isError" type="error" :title="(error as Error)?.message ?? 'Failed to load job'" />

    <template v-else-if="job">
      <!-- Training chart -->
      <n-card title="Training Progress" :bordered="true">
        <TrainingChart :events="events" />
      </n-card>

      <!-- Event log -->
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

      <!-- Artifacts -->
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
                @click="onDownload(artifact.id, artifact.uri)"
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
import { useQuery, useMutation, useQueryClient } from "@tanstack/vue-query";
import { useDialog, useMessage, NTag, NEllipsis } from "naive-ui";
import type { DataTableColumns } from "naive-ui";
import { api, API_BASE } from "../api";
import type { JobStatus, TrainingEvent } from "../types";
import { useJobEvents } from "../composables/useJobEvents";
import TrainingChart from "../components/TrainingChart.vue";

const route = useRoute();
const router = useRouter();
const dialog = useDialog();
const message = useMessage();
const qc = useQueryClient();

// ---------------------------------------------------------------------------
// Route param — reactive so useJobEvents can watch it
// ---------------------------------------------------------------------------

const id = computed(() => route.params.id as string);

// ---------------------------------------------------------------------------
// Job query
// ---------------------------------------------------------------------------

const {
  data: job,
  isLoading,
  isError,
  error,
} = useQuery({
  queryKey: computed(() => ["jobs", id.value]),
  queryFn: () => api.getJob(id.value),
  refetchInterval: 5000,
});

// ---------------------------------------------------------------------------
// SSE live events
// ---------------------------------------------------------------------------

const { events, status: sseStatus } = useJobEvents(id);

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Event log table
// ---------------------------------------------------------------------------

const sortedEvents = computed<TrainingEvent[]>(() =>
  [...events.value].sort((a, b) => {
    // Sort newest-first: compare ts strings (ISO format sorts lexicographically)
    if (a.ts < b.ts) return 1;
    if (a.ts > b.ts) return -1;
    return 0;
  })
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
        { default: () => row.level }
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
        { default: () => truncateJson(row.payload) }
      ),
  },
]);

// ---------------------------------------------------------------------------
// Cancel job
// ---------------------------------------------------------------------------

const cancelMutation = useMutation({
  mutationFn: () => api.cancelJob(id.value),
  onSuccess: () => {
    message.success("Job cancelled");
    qc.invalidateQueries({ queryKey: ["jobs", id.value] });
    qc.invalidateQueries({ queryKey: ["jobs"] });
  },
  onError: (err: Error) => {
    message.error(err.message ?? "Failed to cancel job");
  },
});

function onCancelClick() {
  dialog.warning({
    title: "Confirm",
    content: "Are you sure you want to cancel this job? This action cannot be undone.",
    positiveText: "Cancel Job",
    negativeText: "Go Back",
    onPositiveClick: () => {
      cancelMutation.mutate();
    },
  });
}

// ---------------------------------------------------------------------------
// Artifact download
// ---------------------------------------------------------------------------

const downloadingId = ref<string | null>(null);

async function onDownload(artifactId: string, uri: string) {
  downloadingId.value = artifactId;
  try {
    // api.downloadArtifact returns ArtifactRef (JSON); the actual bytes live at
    // the download URL. Open the endpoint URL in a new tab for direct download.
    const downloadUrl = `${API_BASE}/artifacts/${encodeURIComponent(artifactId)}/download`;
    window.open(downloadUrl, "_blank");
  } catch (err) {
    message.error((err as Error)?.message ?? "Download failed");
  } finally {
    downloadingId.value = null;
  }
}
</script>
