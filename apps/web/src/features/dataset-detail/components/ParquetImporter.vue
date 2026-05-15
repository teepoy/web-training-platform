<script setup lang="ts">
import { ref } from "vue";
import { useMessage } from "naive-ui";
import type { ImporterProps } from "@platform/widget-sdk";
import { API_BASE } from "@platform/web-ui/api/client";

const props = defineProps<ImporterProps>();
const message = useMessage();

const file = ref<File | null>(null);
const loading = ref(false);
const result = ref<{ imported: number; failed: number; errors: string[] } | null>(null);

function onFileChange(e: Event) {
  const target = e.target as HTMLInputElement;
  file.value = target.files?.[0] ?? null;
  result.value = null;
}

async function submit() {
  if (!file.value) {
    message.error("Select a Parquet file to import");
    return;
  }

  loading.value = true;
  try {
    const form = new FormData();
    form.append("file", file.value);
    form.append("dataset_id", props.datasetId);

    const resp = await fetch(
      `${API_BASE}/plugins/import-parquet/import?dataset_id=${encodeURIComponent(props.datasetId)}`,
      { method: "POST", body: form },
    );

    if (!resp.ok) {
      let detail = `Import failed: ${resp.status}`;
      try {
        const body = await resp.json();
        detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
      } catch {}
      throw new Error(detail);
    }

    const data = (await resp.json()) as {
      imported: number;
      failed: number;
      errors: string[];
    };
    result.value = data;
    message.success(`Imported ${data.imported} samples`);
    props.onComplete({
      imported: data.imported,
      failed: data.failed,
      message: data.errors?.length
        ? `Imported with warnings: ${data.errors.join("; ")}`
        : "Parquet import complete",
    });
  } catch (error) {
    message.error(`Parquet import failed: ${(error as Error).message}`);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div>
    <n-space vertical>
      <n-form-item label="Parquet File">
        <input type="file" accept=".parquet,application/octet-stream" @change="onFileChange" />
      </n-form-item>

      <n-alert v-if="file" type="info" :show-icon="false">
        {{ file.name }} ({{ (file.size / 1024).toFixed(1) }} KB)
      </n-alert>

      <n-alert v-if="result" type="success" :show-icon="false">
        Imported {{ result.imported }} samples
        <span v-if="result.failed > 0">, {{ result.failed }} failed</span>
        <ul v-if="result.errors.length" style="margin: 4px 0 0; padding-left: 20px; font-size: 12px">
          <li v-for="w in result.errors" :key="w">{{ w }}</li>
        </ul>
      </n-alert>

      <n-space justify="end">
        <n-button @click="props.onCancel()">Cancel</n-button>
        <n-button type="primary" :loading="loading" :disabled="!file" @click="submit">
          Import
        </n-button>
      </n-space>
    </n-space>
  </div>
</template>
