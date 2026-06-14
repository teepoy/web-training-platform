<template>
  <div data-testid="datasets-shim-sc">
    <DatasetToolbar title="Semiconductor Datasets" />

    <n-alert type="info" style="margin-bottom: 16px">
      Semiconductor inspection workspace — wafer defect classification and review.
    </n-alert>

    <n-data-table
      :columns="columns"
      :data="datasets"
      :row-key="(row: DatasetListItem) => row.id"
      :bordered="false"
      size="small"
      @update:checked-row-keys="handleCheckedRowKeysChange"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, h } from "vue";
import type { DataTableColumns } from "naive-ui";
import { NAlert, NButton, NDataTable, NTag, NText } from "naive-ui";
import { DatasetToolbar } from "@/shared";
import type { DatasetListItem } from "@/shared/datasets/types";

const props = defineProps<{
  datasets: DatasetListItem[];
  currentOrgId: string | null;
  isSuperadmin: boolean;
}>();

const emit = defineEmits<{
  view: [id: string];
  "toggle-public": [payload: { id: string; isPublic: boolean }];
  delete: [row: DatasetListItem];
}>();

function handleCheckedRowKeysChange(_keys: (string | number)[]) {
  // Reserved for batch operations
}

const columns = computed<DataTableColumns<DatasetListItem>>(
  () => [
    {
      title: "Name",
      key: "name",
      width: 220,
      render(row) {
        return h(NText, { style: "font-weight: 500" }, { default: () => row.name });
      },
    },
    {
      title: "Inspection Time",
      key: "inspection_time",
      width: 200,
      render(row) {
        const time =
          (row as any).dataset_meta?.inspection_time;
        if (!time) {
          return h(NText, { depth: "3", italic: true }, { default: () => "—" });
        }
        return h(NText, {}, { default: () => String(time) });
      },
    },
    {
      title: "Task Type",
      key: "task_type",
      width: 150,
      render() {
        return h(
          NTag,
          { type: "info", size: "small", bordered: false },
          { default: () => "Semiconductor" },
        );
      },
    },
    {
      title: "Samples",
      key: "sample_count",
      width: 100,
      render(row) {
        const count =
          (row as any).dataset_meta?.sample_count;
        if (count === undefined || count === null) {
          return h(NText, { depth: "3" }, { default: () => "0" });
        }
        return h(NText, {}, { default: () => String(count) });
      },
    },
    {
      title: "Actions",
      key: "actions",
      width: 100,
      render(row) {
        return h(
          NButton,
          {
            size: "small",
            quaternary: true,
            onClick: () => emit("view", row.id),
          },
          { default: () => "View" },
        );
      },
    },
  ],
);
</script>
