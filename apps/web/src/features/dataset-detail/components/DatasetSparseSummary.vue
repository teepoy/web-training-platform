<script setup lang="ts">
import { computed, h } from "vue";
import { NCard, NDataTable, NDescriptions, NDescriptionsItem, NResult, NSpace, NSpin, NTag, NText, type DataTableColumns } from "naive-ui";
import type { SparseSummaryResponse } from "../../../types";

const schemaColumns: DataTableColumns<{ name: string; type: string }> = [
  { title: "Column", key: "name", render: (row) => h("code", { style: "font-size: 12px" }, row.name) },
  { title: "Type", key: "type", render: (row) => h("span", { style: "font-size: 12px" }, row.type) },
];

const shardColumns: DataTableColumns<{ shard_index: number; row_count: number; format: string; byte_size: number }> = [
  { title: "Shard #", key: "shard_index", width: 90, render: (row) => h("span", {}, String(row.shard_index)) },
  { title: "Rows", key: "row_count", width: 100, render: (row) => h("span", {}, row.row_count.toLocaleString()) },
  { title: "Format", key: "format", width: 90, render: (row) => h("span", {}, row.format) },
  { title: "Size", key: "byte_size", render: (row) => h("span", {}, formatBytes(row.byte_size)) },
];

const props = defineProps<{
  datasetId: string;
  sparseSummary: SparseSummaryResponse | null;
  isLoading: boolean;
}>();

const sampleRowColumns = computed<DataTableColumns<Record<string, unknown>>>(() => {
  if (!props.sparseSummary?.sample_rows.length) return [];
  const keys = Object.keys(props.sparseSummary.sample_rows[0] ?? {});
  return keys.map((key) => ({
    title: key,
    key,
    width: Math.max(80, Math.min(200, key.length * 10 + 40)),
    render: (row: Record<string, unknown>) => {
      const value = row[key];
      if (value === null || value === undefined) return h("span", { style: "color: #999" }, "—");
      const text = typeof value === "string" ? value : JSON.stringify(value);
      return h("span", { style: "font-size: 12px; font-family: monospace" }, text.length > 80 ? `${text.slice(0, 80)}…` : text);
    },
  }));
});

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}
</script>

<template>
  <n-result
    status="info"
    title="Sparse Dataset"
    description="This dataset uses file-backed sparse storage. Individual sample browsing is not available."
    style="margin-top: 48px"
  >
    <template #footer>
      <n-space vertical size="large" align="center" style="max-width: 700px; width: 100%">
        <n-spin v-if="isLoading" size="small" />

        <template v-else-if="sparseSummary">
          <n-card title="Manifest" size="small" style="width: 100%">
            <n-descriptions label-placement="left" :column="2" size="small" bordered>
              <n-descriptions-item label="Dataset">{{ sparseSummary.name }}</n-descriptions-item>
              <n-descriptions-item label="Type">{{ sparseSummary.dataset_type }}</n-descriptions-item>
              <n-descriptions-item label="Storage Mode">
                <n-tag type="info" size="small">{{ sparseSummary.storage_mode }}</n-tag>
              </n-descriptions-item>
              <n-descriptions-item label="Total Shards">{{ sparseSummary.manifest.shard_count }}</n-descriptions-item>
              <n-descriptions-item label="Total Rows">{{ sparseSummary.manifest.total_rows.toLocaleString() }}</n-descriptions-item>
              <n-descriptions-item label="Created">{{ new Date(sparseSummary.manifest.created_at).toLocaleString() }}</n-descriptions-item>
            </n-descriptions>
          </n-card>

          <n-card v-if="sparseSummary.manifest.schema_columns.length > 0" title="Schema" size="small" style="width: 100%">
            <n-data-table :columns="schemaColumns" :data="sparseSummary.manifest.schema_columns" :bordered="true" :single-line="false" size="small" />
          </n-card>

          <n-card v-if="sparseSummary.shards.length > 0" title="Shards" size="small" style="width: 100%">
            <n-data-table :columns="shardColumns" :data="sparseSummary.shards" :bordered="true" :single-line="false" size="small" />
          </n-card>

          <n-card v-if="sparseSummary.sample_rows.length > 0" title="Preview Rows (first shard)" size="small" style="width: 100%">
            <n-data-table :columns="sampleRowColumns" :data="sparseSummary.sample_rows" :bordered="true" :single-line="false" size="small" :max-height="300" />
          </n-card>
        </template>

        <n-text v-else depth="3">Unable to load sparse summary.</n-text>
      </n-space>
    </template>
  </n-result>
</template>
