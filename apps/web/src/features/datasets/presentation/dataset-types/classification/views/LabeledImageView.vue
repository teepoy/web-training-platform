<template>
  <div data-testid="view-labeled-image-v1">
    <n-empty
      v-if="!items.length"
      description="No labeled samples in this view. Add samples to this dataset first."
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
import { NEmpty, NImage, NDataTable, NText, NTag, NEllipsis } from "naive-ui";
import type { LabeledImageV1Row } from "@/shared/api/types";

withDefaults(
  defineProps<{
    datasetId?: string;
    items?: LabeledImageV1Row[];
    total?: number;
  }>(),
  {
    items: () => [],
    total: 0,
  },
);

const columns: DataTableColumns<LabeledImageV1Row> = [
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
    key: "label",
    title: "Label",
    width: 180,
    render(row) {
      return h(
        NTag,
        { type: "info", size: "small", bordered: false },
        { default: () => row.label },
      );
    },
  },
];
</script>
