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
const rowCount = ref<number | null>(null);
const statusMessage = ref("");

async function runExport() {
  loading.value = true;
  statusMessage.value = t("datasetFlows.startingParquet");
  try {
    const event = await streamApiSse(
      `/plugins/export-parquet/export/stream?dataset_id=${encodeURIComponent(props.datasetId)}`,
      {
        method: "POST",
        onEvent: (item) => {
          if (item.event_type === "progress") {
            statusMessage.value = item.message || item.status || t("datasetFlows.exporting");
          }
        },
      },
    );
    const payload = event?.payload ?? {};
    const resultUri = typeof payload.uri === "string" ? payload.uri : null;
    if (!resultUri) throw new Error(t("datasetFlows.missingParquetUri"));
    uri.value = resultUri;
    rowCount.value = typeof payload.rows === "number" ? payload.rows : null;
    statusMessage.value = t("datasetFlows.parquetComplete");
    message.success(t("datasetFlows.parquetExportSuccess", { count: rowCount.value ?? "?" }));
  } catch (error) {
    message.error(toUserMessage(error, t("datasetFlows.parquetFailed")));
  } finally {
    loading.value = false;
  }
}

function done() {
  props.onComplete({
    format: "parquet",
    url: uri.value ?? undefined,
    message: t("datasetFlows.parquetExportSummary", { count: rowCount.value ?? "?" }),
  });
}
</script>

<template>
  <div>
    <n-space vertical>
      <n-button type="primary" :loading="loading" @click="runExport">
        {{ t("datasetFlows.exportParquet") }}
      </n-button>
      <n-text v-if="statusMessage" depth="3">{{ statusMessage }}</n-text>

      <n-space v-if="uri" vertical :size="4">
        <template v-if="rowCount !== null">
          <n-text>{{ t("datasetFlows.parquetRowsExported", { count: rowCount }) }}</n-text>
        </template>
        <n-button tag="a" :href="buildExportDownloadUrl(uri)" download type="primary">
          {{ t("datasetFlows.downloadParquet") }}
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
