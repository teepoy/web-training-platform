<template>
  <div data-testid="view-box-detection-v1">
    <n-empty
      v-if="!items.length"
      description="No detection samples in this view. Add detection samples to this dataset first."
      style="margin-top: 24px"
    />
    <n-data-table
      v-else
      :columns="columns"
      :data="items"
      :bordered="false"
      :single-line="false"
      size="small"
    />
  </div>
</template>

<script setup lang="ts">
import { h } from "vue";
import type { DataTableColumns } from "naive-ui";
import { NEmpty, NImage, NDataTable, NText, NTag, NSpace, NEllipsis } from "naive-ui";
import type { BoxDetectionV1Row } from "@/shared/api/types";

withDefaults(
  defineProps<{
    datasetId?: string;
    items?: BoxDetectionV1Row[];
    total?: number;
  }>(),
  {
    items: () => [],
    total: 0,
  },
);

const columns: DataTableColumns<BoxDetectionV1Row> = [
  {
    key: "sample_id",
    title: "Sample ID",
    width: 200,
    render(row) {
      return h(NEllipsis, null, {
        default: () =>
          h(
            NText,
            { depth: "3", style: { fontFamily: "monospace", fontSize: "12px" } },
            { default: () => row.sample_id },
          ),
      });
    },
  },
  {
    key: "image_uris",
    title: "Image",
    width: 120,
    render(row) {
      const uri = row.image_uris?.[0];
      if (!uri) {
        return h(NText, { depth: "3", italic: true }, { default: () => "—" });
      }
      return h(NImage, {
        src: uri,
        width: 80,
        height: 60,
        objectFit: "cover",
        fallbackSrc: "",
        showToolbar: false,
        style: { borderRadius: "4px" },
      });
    },
  },
  {
    key: "boxes_count",
    title: "Boxes",
    width: 100,
    render(row) {
      const count = row.boxes?.length ?? 0;
      return h(
        NTag,
        { type: count > 0 ? "success" : "default", size: "small", bordered: false },
        { default: () => `${count}` },
      );
    },
  },
  {
    key: "boxes_labels",
    title: "Labels",
    minWidth: 160,
    render(row) {
      const boxes = row.boxes ?? [];
      if (!boxes.length) {
        return h(NText, { depth: "3", italic: true }, { default: () => "—" });
      }
      const uniqueLabels = [...new Set(boxes.map((b) => b.label))];
      return h(
        NSpace,
        { wrap: true, size: [4, 4] },
        {
          default: () =>
            uniqueLabels.map((label) =>
              h(
                NTag,
                { key: label, type: "info", size: "small", bordered: false },
                { default: () => label },
              ),
            ),
        },
      );
    },
  },
];
</script>
