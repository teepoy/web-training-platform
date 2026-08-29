<script setup lang="ts">
import { NButton } from "naive-ui";
import { useI18n } from "vue-i18n";

import type { DatasetListItem } from "../../../datasets/types";

const { t } = useI18n();

const props = withDefaults(
  defineProps<{
    row: DatasetListItem;
    isSuperadmin: boolean;
    isOwnOrg: boolean;
    canDelete: boolean;
    canRename?: boolean;
  }>(),
  {
    canRename: true,
  },
);

const emit = defineEmits<{
  view: [id: string];
  rename: [row: DatasetListItem];
  delete: [row: DatasetListItem];
}>();

function onView(e: MouseEvent): void {
  e.stopPropagation();
  emit("view", props.row.id);
}

function onRename(e: MouseEvent): void {
  e.stopPropagation();
  emit("rename", props.row);
}

function onDelete(e: MouseEvent): void {
  e.stopPropagation();
  emit("delete", props.row);
}
</script>

<template>
  <span>
    <NButton size="small" @click="onView">{{ t("jobs.view") }}</NButton>
    <NButton v-if="canRename" size="small" style="margin-left: 6px" @click="onRename">
      {{ t("common.rename") }}
    </NButton>
    <template v-if="canDelete">
      <NButton size="small" type="error" style="margin-left: 6px" @click="onDelete">
        {{ t("common.delete") }}
      </NButton>
    </template>
  </span>
</template>
