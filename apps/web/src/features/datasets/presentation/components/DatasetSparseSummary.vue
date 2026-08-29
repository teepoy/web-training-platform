<script setup lang="ts">
import { computed, h } from "vue";
import { useI18n } from "vue-i18n";
import { NDataTable, NTag, type DataTableColumns } from "naive-ui";
import type { SparseSummaryResponse } from "@/generated/orval/models";
import { formatDateTime, formatFileSize, formatNumber } from "@/shared/i18n/format";

const { t } = useI18n();

const schemaColumns: DataTableColumns<{ name: string; type: string }> = [
  {
    title: t("datasetFlows.column"),
    key: "name",
    render: (row) => h("code", { style: "font-size: 12px" }, row.name),
  },
  {
    title: t("datasetFlows.type"),
    key: "type",
    render: (row) => h("span", { style: "font-size: 12px" }, row.type),
  },
];

const shardColumns: DataTableColumns<{
  shard_index: number;
  row_count: number;
  format: string;
  byte_size: number;
}> = [
  {
    title: t("datasetFlows.shardNumber"),
    key: "shard_index",
    width: 90,
    render: (row) => h("span", {}, String(row.shard_index)),
  },
  {
    title: t("datasetFlows.rows"),
    key: "row_count",
    width: 100,
    render: (row) => h("span", {}, formatNumber(row.row_count)),
  },
  {
    title: t("datasetFlows.format"),
    key: "format",
    width: 90,
    render: (row) => h("span", {}, row.format),
  },
  {
    title: t("datasetFlows.size"),
    key: "byte_size",
    render: (row) => h("span", {}, formatFileSize(row.byte_size)),
  },
];

const props = defineProps<{
  datasetId: string;
  sparseSummary: SparseSummaryResponse | null;
  isLoading: boolean;
}>();

const emit = defineEmits<{
  (e: "select-sample", sampleId: string): void;
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
      if (value === null || value === undefined) {
        return h("span", { style: "color: #999" }, "—");
      }
      const text = typeof value === "string" ? value : JSON.stringify(value);
      return h(
        "span",
        { style: "font-size: 12px; font-family: monospace" },
        text.length > 80 ? `${text.slice(0, 80)}…` : text,
      );
    },
  }));
});

function handleSampleRowClick(row: Record<string, unknown>) {
  const sampleId = String(row.id ?? row.sample_id ?? "");
  if (sampleId) emit("select-sample", sampleId);
}
</script>

<template>
  <section class="sparse-summary">
    <n-alert type="info" :bordered="false">
      {{ t("datasetFlows.sparseHelp") }}
    </n-alert>

    <n-spin :show="isLoading">
      <template v-if="sparseSummary">
        <n-card :title="t('datasetFlows.storageSummary')" size="small">
          <div class="manifest-metrics">
            <div class="manifest-metric">
              <n-text depth="3">{{ t("datasetFlows.shards") }}</n-text>
              <strong>{{ formatNumber(sparseSummary.manifest.shard_count) }}</strong>
            </div>
            <div class="manifest-metric">
              <n-text depth="3">{{ t("datasetFlows.rows") }}</n-text>
              <strong>{{ formatNumber(sparseSummary.manifest.total_rows) }}</strong>
            </div>
            <div class="manifest-metric">
              <n-text depth="3">{{ t("datasetFlows.format") }}</n-text>
              <n-tag type="info" size="small">{{ sparseSummary.storage_mode }}</n-tag>
            </div>
            <div class="manifest-metric">
              <n-text depth="3">{{ t("datasetFlows.created") }}</n-text>
              <strong>{{ formatDateTime(sparseSummary.manifest.created_at) }}</strong>
            </div>
          </div>
        </n-card>

        <div class="sparse-detail-grid">
          <n-card
            v-if="sparseSummary.manifest.schema_columns.length > 0"
            :title="t('datasetFlows.schema')"
            size="small"
          >
            <n-data-table
              :columns="schemaColumns"
              :data="sparseSummary.manifest.schema_columns"
              :bordered="false"
              :single-line="false"
              size="small"
            />
          </n-card>

          <n-card
            v-if="sparseSummary.shards.length > 0"
            :title="t('datasetFlows.shards')"
            size="small"
          >
            <n-data-table
              :columns="shardColumns"
              :data="sparseSummary.shards"
              :bordered="false"
              :single-line="false"
              :scroll-x="420"
              size="small"
            />
          </n-card>
        </div>

        <n-card
          v-if="sparseSummary.sample_rows.length > 0"
          :title="t('datasetFlows.previewRows')"
          size="small"
        >
          <template #header-extra>
            <n-text depth="3">{{ t("datasetFlows.firstShard") }}</n-text>
          </template>
          <n-data-table
            :columns="sampleRowColumns"
            :data="sparseSummary.sample_rows"
            :bordered="false"
            :single-line="false"
            :scroll-x="Math.max(680, sampleRowColumns.length * 140)"
            size="small"
            :max-height="320"
            :row-props="
              (row: Record<string, unknown>) => ({
                style: 'cursor: pointer',
                onClick: () => handleSampleRowClick(row),
              })
            "
          />
        </n-card>
      </template>

      <n-empty v-else-if="!isLoading" :description="t('datasetFlows.sparseLoadFailed')" />
    </n-spin>
  </section>
</template>

<style scoped>
.sparse-summary {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 16px;
}

.manifest-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 18px;
}

.manifest-metric {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.manifest-metric strong {
  overflow-wrap: anywhere;
  font-weight: 600;
}

.sparse-detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

@media (max-width: 900px) {
  .manifest-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .sparse-detail-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 520px) {
  .manifest-metrics {
    grid-template-columns: 1fr;
  }
}
</style>
