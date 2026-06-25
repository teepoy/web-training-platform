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
  delete: [row: DatasetListItem];
}>();

function onView(e: MouseEvent): void {
  e.stopPropagation();
  emit("view", props.row.id);
}

function onDelete(e: MouseEvent): void {
  e.stopPropagation();
  emit("delete", props.row);
}
</script>

<template>
  <span>
    <NButton size="small" @click="onView">View</NButton>
    <template v-if="canDelete">
      <NButton size="small" type="error" style="margin-left: 6px" @click="onDelete">
        Delete
      </NButton>
    </template>
  </span>
</template>
