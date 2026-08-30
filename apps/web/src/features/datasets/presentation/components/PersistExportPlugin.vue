<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { useMessage } from "naive-ui";
import type { ExporterProps } from "@/shared/widgets/sdk";
import { buildExportDownloadUrl } from "@/shared/api/datasets";
import { streamApiSse } from "@/shared/api/sse";
import { toUserMessage } from "@/shared/api";

const props = defineProps<ExporterProps>();
const message = useMessage();
const { t } = useI18n();

const loading = ref(false);
const uri = ref<string | null>(null);
const statusMessage = ref("");

async function runPersist() {
  loading.value = true;
  statusMessage.value = t("datasetFlows.startingExport");
  try {
    const event = await streamApiSse(
      `/exports/${encodeURIComponent(props.datasetId)}/persist/stream`,
      {
        method: "POST",
        onEvent: (item) => {
          if (item.event_type === "progress") {
            statusMessage.value = item.message || item.status || t("datasetFlows.exporting");
          }
        },
      },
    );
    const resultUri = typeof event?.payload?.uri === "string" ? event.payload.uri : null;
    if (!resultUri) throw new Error(t("datasetFlows.missingExportUri"));
    uri.value = resultUri;
    statusMessage.value = t("datasetFlows.exportPersisted");
    message.success(t("datasetFlows.exportPersistedSuccess"));
  } catch (error) {
    message.error(toUserMessage(error, t("datasetFlows.persistFailed")));
  } finally {
    loading.value = false;
  }
}

function done() {
  props.onComplete({
    format: "persist",
    url: uri.value ?? undefined,
    message: t("datasetFlows.exportPersisted"),
  });
}
</script>

<template>
  <div>
    <n-space vertical>
      <n-button type="primary" :loading="loading" @click="runPersist">
        {{ t("datasetFlows.persistExport") }}
      </n-button>
      <n-text v-if="statusMessage" depth="3">{{ statusMessage }}</n-text>
      <n-space v-if="uri" vertical :size="4">
        <n-button tag="a" :href="buildExportDownloadUrl(uri)" download type="primary">
          {{ t("datasetFlows.downloadExport") }}
        </n-button>
        <n-text depth="3" style="font-size: 11px; word-break: break-all">
          {{ t("datasetFlows.uriLabel") }}: {{ uri }}
        </n-text>
      </n-space>
      <n-space justify="end">
        <n-button @click="props.onCancel()">{{ t("datasetFlows.close") }}</n-button>
        <n-button type="success" :disabled="!uri" @click="done">{{ t("common.done") }}</n-button>
      </n-space>
    </n-space>
  </div>
</template>
