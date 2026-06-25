<script setup lang="ts">
import { NButton } from "naive-ui";

import type { DatasetListItem } from "../../../datasets/types";

const props = defineProps<{
  row: DatasetListItem;
  isSuperadmin: boolean;
  isOwnOrg: boolean;
  canDelete: boolean;
}>();

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
    <NButton size="small" @click="onView">View</NButton>
    <NButton size="small" style="margin-left: 6px" @click="onRename">Rename</NButton>
    <template v-if="canDelete">
      <NButton size="small" type="error" style="margin-left: 6px" @click="onDelete">
        Delete
      </NButton>
    </template>
  </span>
</template>
